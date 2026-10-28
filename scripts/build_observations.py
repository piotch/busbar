# /// script
# requires-python = ">=3.11"
# dependencies = ["rdflib>=7.1,<8", "pyshacl>=0.30,<1"]
# ///
"""Export archived catalogue observations as separate named graphs in TriG."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from rdflib import Dataset, Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

from capture_catalogue import ROOT, load_declarations
from artifact_store import artifact_bytes, manifest_reference

PUB = Namespace("https://busbar.example/publishing#")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
DCT = Namespace("http://purl.org/dc/terms/")
DEFINITIONS = URIRef("https://busbar.example/graphs/current-definitions")
METADATA = URIRef("https://busbar.example/graphs/observations")
CURATED = URIRef("https://busbar.example/graphs/busbar-catalogue")


def build(observation_paths):
    paths = sorted(observation_paths)
    if not paths:
        raise ValueError("No observations found; run scripts/capture_catalogue.py first")
    dataset = Dataset(default_union=False)
    for prefix, namespace in (("pub", PUB), ("prov", PROV), ("dcat", DCAT), ("dct", DCT)):
        dataset.bind(prefix, namespace)
    declarations, _ = load_declarations()
    definitions = dataset.graph(DEFINITIONS)
    for triple in declarations:
        definitions.add(triple)
    # Curator assertions remain separate from definitions and publisher snapshots.
    dataset.graph(CURATED).parse(ROOT / "catalogue.ttl", format="turtle")
    metadata = dataset.graph(METADATA)
    seen = set()
    summary = []
    for path in paths:
        record = json.loads(path.read_text())
        status = record["status"]
        if status not in ("success", "failed"):
            raise ValueError(f"Unsupported observation status in {path}: {status}")
        timestamp = datetime.fromisoformat(record["observed_at"])
        if timestamp.tzinfo is None:
            raise ValueError(f"Observation timestamp lacks a timezone: {path}")
        catalog = URIRef(record["catalog"])
        observation = URIRef(str(catalog) + "/observations/" + record["observation_id"])
        if observation in seen:
            raise ValueError(f"Duplicate observation identity: {observation}")
        seen.add(observation)
        metadata.add((observation, RDF.type, PUB.ObservationRecord))
        metadata.add((observation, PUB.observedCatalog, catalog))
        metadata.add((observation, PUB.status, Literal(status)))
        metadata.add((observation, PUB.specification, URIRef(record["specification"])))
        metadata.add((observation, PROV.generatedAtTime,
                      Literal(record["observed_at"], datatype=XSD.dateTime)))
        metadata.add((observation, PROV.wasDerivedFrom, URIRef(manifest_reference(record, path))))
        if record.get("source_url"):
            metadata.add((observation, DCT.source, URIRef(record["source_url"])))
        if record.get("content_hash"):
            metadata.add((observation, PUB.contentHash, Literal(record["content_hash"])))
        if record.get("artifact_uri"):
            metadata.add((observation, PROV.wasDerivedFrom, URIRef(record["artifact_uri"])))
        if status == "failed":
            if record.get("error"):
                metadata.add((observation, PUB.error, Literal(record["error"])))
            # A failed request is NOT an empty catalogue snapshot.
            summary.append((str(observation), status, None))
            continue
        # Parse each capture independently: blank nodes are scoped per observation.
        # No canonical identity rewrite, labels, or current declarations enter it.
        captured = Graph().parse(data=artifact_bytes(record, path), format="xml")
        source_catalogs = set(captured.subjects(RDF.type, DCAT.Catalog))
        if not source_catalogs:
            raise ValueError(f"No dcat:Catalog in artifact for {path}")
        members = set(captured.subjects(RDF.type, DCAT.Dataset))
        if any(not isinstance(node, URIRef) for node in members):
            raise ValueError(f"Dataset identities must be IRIs: {path}")
        if len(members) != record["dataset_count"]:
            raise ValueError(f"Dataset count mismatch: {path}")
        if "triple_count" in record and len(captured) != record["triple_count"]:
            raise ValueError(f"Triple count mismatch: {path}")
        snapshot = dataset.graph(observation)
        for triple in captured:
            snapshot.add(triple)
        metadata.add((observation, RDF.type, PUB.CatalogSnapshot))
        metadata.add((observation, PUB.datasetCount, Literal(len(members), datatype=XSD.integer)))
        for source in source_catalogs:
            metadata.add((observation, PROV.hadPrimarySource, source))
        summary.append((str(observation), status, len(members)))
    return dataset, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=ROOT / "captures")
    parser.add_argument("--output", type=Path, default=ROOT / "build/observations.trig")
    parser.add_argument("--observation", type=Path, action="append",
                        help="Select observation manifests explicitly; repeat as needed")
    args = parser.parse_args()
    paths = args.observation if args.observation else args.captures.joinpath("observations").glob("*.json")
    dataset, summary = build(paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Don't replace a previous export unless serialization and parsing succeed.
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        dataset.serialize(destination=str(temporary), format="trig")
        reloaded = Dataset(default_union=False)
        reloaded.parse(temporary, format="trig")
        before = {g.identifier: len(g) for g in dataset.graphs() if len(g)}
        after = {g.identifier: len(g) for g in reloaded.graphs() if len(g)}
        if before != after:
            raise ValueError("TriG round-trip changed graph identities or triple counts")
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Built {args.output.resolve()}")
    print(f"{len(summary)} observation records; {sum(s == 'success' for _, s, _ in summary)} snapshot graphs")
    for identifier, status, count in summary:
        print(f"  {identifier}: {status}" + (f", {count} datasets" if count is not None else ""))


if __name__ == "__main__":
    main()
