# /// script
# requires-python = ">=3.11"
# dependencies = ["rdflib>=7.1,<8", "pyshacl>=0.30,<1"]
# ///
"""Validate Git-managed declarations and archive a declared DCAT RDF/XML export.

Run with uv; dependencies are isolated from the application's environment.
No scheduling, messaging, database loading or dataset downloads are performed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import uuid

from pyshacl import validate
from rdflib import Graph, Namespace, RDF, URIRef

from artifact_store import storage_reference

ROOT = Path(__file__).resolve().parents[1]
PUB = Namespace("https://busbar.example/publishing#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
DEFAULT_SPEC = "https://busbar.example/id/grid/uk/dno/ukpn/catalogue/captures/dcat"
MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 1000
HYDRA = Namespace("http://www.w3.org/ns/hydra/core#")


def next_catalogue_page(graph, endpoint):
    """Use CKAN's page number on the declared endpoint, not its advertised host.

    Some portals advertise a frontend host that cannot serve RDF. Never follow
    arbitrary publisher URLs; only a single increasing integer page is accepted.
    """
    links = set(graph.objects(None, HYDRA.nextPage)) | set(graph.objects(None, HYDRA.next))
    if not links:
        return None
    if len(links) != 1:
        raise ValueError("Ambiguous catalogue pagination")
    page = parse_qs(urlsplit(str(next(iter(links)))).query).get("page", [])
    if len(page) != 1 or not page[0].isdigit() or int(page[0]) < 1:
        raise ValueError("Invalid catalogue page number")
    parts = urlsplit(endpoint)
    query = parse_qs(parts.query)
    query["page"] = page
    return urlunsplit(parts._replace(query=urlencode(query, doseq=True)))


def load_declarations(root=ROOT):
    paths = sorted([
        *root.joinpath("definitions").rglob("*.ttl"),
        *root.joinpath("vocabulary").rglob("*.ttl"),
    ])
    graph = Graph()
    hashes = {}
    for path in paths:
        content = path.read_bytes()
        graph.parse(data=content, format="turtle")
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    shapes = Graph().parse(root / "shapes/publishing.ttl", format="turtle")
    conforms, _, report = validate(graph, shacl_graph=shapes, inference="none")
    if not conforms:
        raise ValueError(str(report))
    return graph, hashes


def capture_parameters(graph, spec):
    node = URIRef(spec)
    if (node, RDF.type, PUB.CaptureSpecification) not in graph:
        raise ValueError(f"Unknown capture specification: {spec}")
    catalog = str(graph.value(node, PUB.catalog))
    endpoint = str(graph.value(node, PUB.endpoint))
    media_type = str(graph.value(node, PUB.mediaType))
    if not endpoint.startswith("https://") or media_type != "application/rdf+xml":
        raise ValueError("Only HTTPS RDF/XML catalogue exports are supported")
    return catalog, endpoint, media_type


def parse_catalogue(content):
    graph = Graph().parse(data=content, format="xml")
    if not any(graph.subjects(RDF.type, DCAT.Catalog)):
        raise ValueError("Response is RDF but contains no dcat:Catalog")
    # Return source identities, without assigning Busbar identities or editions.
    datasets = set(graph.subjects(RDF.type, DCAT.Dataset))
    if any(not isinstance(node, URIRef) for node in datasets):
        raise ValueError("Dataset membership comparison requires source dataset IRIs")
    return sorted(map(str, datasets)), len(graph)


def store_artifact(output, content):
    digest = hashlib.sha256(content).hexdigest()
    path = output / "objects" / "sha256" / f"{digest}.rdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ValueError(f"Existing artifact does not match its hash: {path}")
    return digest, path.resolve().as_uri()


def previous_success(output, spec):
    candidates = []
    for path in output.joinpath("observations").glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("specification") == spec and record.get("status") == "success":
            candidates.append(record)
    return max(candidates, key=lambda row: row["observed_at"], default=None)


def git_revision():
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def capture(graph, hashes, spec, output, storage_uri=None):
    if storage_uri:
        storage_reference(storage_uri, "observations/")  # Validate before acquisition.
    catalog, endpoint, media_type = capture_parameters(graph, spec)
    previous = previous_success(output, spec)
    record = {
        "schema_version": 1,
        "observation_id": str(uuid.uuid4()),
        "specification": spec,
        "catalog": catalog,
        "source_url": endpoint,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision(),
        # Exact declaration hashes remain useful with uncommitted changes.
        "declaration_hashes": hashes,
        "status": "failed",
    }
    try:
        url, seen, total_bytes = endpoint, set(), 0
        combined = Graph()
        record["pages"] = []
        while url:
            if url in seen or len(seen) >= MAX_PAGES:
                raise ValueError("Catalogue pagination cycle or page limit exceeded")
            seen.add(url)
            request = Request(url, headers={
                "Accept": media_type,
                "User-Agent": "Busbar-catalogue-observer/0.1",
            })
            with urlopen(request, timeout=60) as response:
                metadata = {
                    "source_url": url, "http_status": response.status,
                    "final_url": response.url,
                    "content_type": response.headers.get("Content-Type"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
                content = response.read(MAX_BYTES - total_bytes + 1)
            total_bytes += len(content)
            if total_bytes > MAX_BYTES:
                raise ValueError("Catalogue exceeds the 50 MiB capture limit")
            # Preserve every original page, including malformed responses.
            digest, artifact_uri = store_artifact(output, content)
            relative = f"objects/sha256/{digest}.rdf"
            artifact = {
                "content_hash": f"sha256:{digest}", "artifact_path": relative,
                "artifact_uri": storage_reference(storage_uri, relative) if storage_uri else artifact_uri,
            }
            record["pages"].append({**metadata, **artifact})
            if len(seen) == 1:
                record.update({**metadata, **artifact})
            parse_catalogue(content)
            page_graph = Graph().parse(data=content, format="xml")
            combined += page_graph
            next_url = next_catalogue_page(page_graph, endpoint)
            if next_url:
                current_page = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
                next_page = int(parse_qs(urlsplit(next_url).query)["page"][0])
                if next_page <= current_page:
                    raise ValueError("Catalogue pagination must advance")
            url = next_url
        if len(seen) > 1:
            # A derived union for existing readers; raw evidence remains in pages.
            content = combined.serialize(format="xml", encoding="utf-8")
            digest, artifact_uri = store_artifact(output, content)
            relative = f"objects/sha256/{digest}.rdf"
            record.update({
                "artifact_kind": "rdf-page-union",
                "content_hash": f"sha256:{digest}", "artifact_path": relative,
                "artifact_uri": storage_reference(storage_uri, relative) if storage_uri else artifact_uri,
            })
        datasets, triple_count = parse_catalogue(content)
        totals = {int(value) for value in combined.objects(None, HYDRA.totalItems)}
        if totals and totals != {len(datasets)}:
            raise ValueError("Catalogue dataset count does not match pagination total")
        record.update({
            "status": "success",
            "dataset_count": len(datasets),
            "dataset_iris": datasets,
            "triple_count": triple_count,
        })
        if previous:
            old, new = set(previous["dataset_iris"]), set(datasets)
            # Compare original response bytes, not a union serialization whose
            # blank-node labels/order may differ between otherwise equal runs.
            old_hashes = [page["content_hash"] for page in previous.get("pages", [])]
            new_hashes = [page["content_hash"] for page in record["pages"]]
            bytes_changed = (old_hashes != new_hashes if old_hashes
                             else previous["content_hash"] != record["content_hash"])
            record["comparison"] = {
                "previous_observation_id": previous["observation_id"],
                "bytes_changed": bytes_changed,
                "newly_listed": sorted(new - old),
                "no_longer_listed": sorted(old - new),
            }
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        if hasattr(exc, "code"):
            record["http_status"] = exc.code
    record["completed_at"] = datetime.now(timezone.utc).isoformat()
    directory = output / "observations"
    directory.mkdir(parents=True, exist_ok=True)
    filename = record["completed_at"].replace(":", "-") + "-" + record["observation_id"] + ".json"
    destination = directory / filename
    if storage_uri:
        record["manifest_uri"] = storage_reference(storage_uri, "observations/" + filename)
    # Readers never see a partially written observation.
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(destination)
    return record, destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="Capture specification IRI")
    parser.add_argument("--output", type=Path, default=ROOT / "captures")
    parser.add_argument("--storage-uri", help="Portable s3://bucket/prefix references; files are still written locally")
    args = parser.parse_args()
    graph, hashes = load_declarations()
    capture_parameters(graph, args.spec)
    if args.validate_only:
        print(f"Validated {len(hashes)} declaration/vocabulary files")
        return 0
    record, destination = capture(graph, hashes, args.spec, args.output, args.storage_uri)
    print(json.dumps({"observation": str(destination), **record}, indent=2))
    return 0 if record["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
