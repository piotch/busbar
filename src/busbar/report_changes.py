"""Report noteworthy observed catalogue changes as RDF/XML (not data-content changes)."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

from rdflib import BNode, Dataset, Graph, Literal, Namespace, RDF, URIRef
from rdflib.compare import graph_diff, isomorphic, to_isomorphic
from rdflib.namespace import XSD

from .build_observations import DCAT, DCT, METADATA, PROV, PUB

CHANGE = Namespace("https://busbar.example/changes#")


def dataset_view(graph, dataset):
    """Dataset statements, distributions and recursive blank-node descriptions."""
    view = Graph()
    pending = [dataset]
    seen = set()
    while pending:
        subject = pending.pop()
        if subject in seen:
            continue
        seen.add(subject)
        for triple in graph.triples((subject, None, None)):
            view.add(triple)
            _, predicate, obj = triple
            if isinstance(obj, BNode) or predicate == DCAT.distribution:
                pending.append(obj)
    return view


def identity(*values):
    digest = hashlib.sha256("\n".join(map(str, values)).encode()).hexdigest()
    return URIRef("urn:busbar:change-report:" + digest)


def timestamp(metadata, node):
    value = datetime.fromisoformat(str(metadata.value(node, PROV.generatedAtTime)))
    if value.tzinfo is None:
        raise ValueError(f"Observation timestamp lacks a timezone: {node}")
    return value.astimezone(timezone.utc)


def report(archive):
    """Compare latest successful pairs; retain unknown recurrence, suppress repeats.

    Previous-day evidence requires a successful pair ending on that UTC day,
    at most 36 hours apart, with the dataset present in both snapshots. This is
    observation coverage, not proof that the underlying data stayed unchanged.
    """
    graph = Graph()
    for prefix, ns in (("change", CHANGE), ("prov", PROV), ("dcat", DCAT), ("dct", DCT)):
        graph.bind(prefix, ns)
    metadata = archive.graph(METADATA)
    catalogues = {}
    for node in set(metadata.subjects(RDF.type, PUB.CatalogSnapshot)):
        if str(metadata.value(node, PUB.status)) != "success":
            continue
        catalog = metadata.value(node, PUB.observedCatalog)
        if not isinstance(catalog, URIRef):
            raise ValueError(f"Missing catalogue identity: {node}")
        catalogues.setdefault(catalog, []).append((timestamp(metadata, node), node))
    root = identity(*(node for cat in sorted(catalogues, key=str)
                      for _, node in sorted(catalogues[cat])))
    graph.add((root, RDF.type, CHANGE.Report))
    graph.add((root, PROV.generatedAtTime, Literal(datetime.now(timezone.utc), datatype=XSD.dateTime)))
    graph.add((root, PROV.wasAttributedTo, URIRef("https://busbar.example/software/report-changes")))
    definitions = archive.graph(URIRef("https://busbar.example/graphs/current-definitions"))
    for catalog, observations in sorted(catalogues.items(), key=lambda item: str(item[0])):
        observations.sort(key=lambda item: (item[0], str(item[1])))
        if any(a[0] == b[0] for a, b in zip(observations, observations[1:])):
            raise ValueError(f"Ambiguous simultaneous snapshots for {catalog}")
        activity = identity(root, catalog)
        graph.add((root, CHANGE.comparison, activity))
        graph.add((activity, RDF.type, PROV.Activity))
        graph.add((activity, PROV.wasAssociatedWith, URIRef("https://busbar.example/software/report-changes")))
        graph.add((root, PROV.wasGeneratedBy, activity))
        graph.add((activity, CHANGE.catalog, catalog))
        graph.add((activity, CHANGE.snapshotCount, Literal(len(observations))))
        # Preserve declared publisher identity; no inference from catalogue URL paths.
        for publisher in definitions.objects(catalog, DCT.publisher):
            graph.add((catalog, DCT.publisher, publisher))
        for time, node in observations:
            graph.add((activity, PROV.used, node))
            graph.add((root, PROV.wasDerivedFrom, node))
            graph.add((node, PROV.generatedAtTime, Literal(time, datatype=XSD.dateTime)))
        graph.add((activity, CHANGE.latestSnapshot, observations[-1][1]))
        if len(observations) < 2:
            graph.add((activity, CHANGE.comparisonStatus, CHANGE.BaselineOnly))
            continue
        graph.add((activity, CHANGE.comparisonStatus, CHANGE.Compared))
        graph.add((activity, CHANGE.previousSnapshot, observations[-2][1]))
        graphs = [archive.graph(node) for _, node in observations]
        members = [set(g.subjects(RDF.type, DCAT.Dataset)) for g in graphs]
        before, after = members[-2:]
        yesterday = observations[-1][0].date() - timedelta(days=1)
        cache = {}

        def view(i, dataset):
            key = (i, dataset)
            if key not in cache:
                cache[key] = dataset_view(graphs[i], dataset)
            return cache[key]

        for dataset in sorted(before | after, key=str):
            if dataset not in before:
                kind, recurrence = CHANGE.ListingAdded, CHANGE.NotApplicable
            elif dataset not in after:
                kind, recurrence = CHANGE.ListingRemoved, CHANGE.NotApplicable
            else:
                if isomorphic(view(-2, dataset), view(-1, dataset)):
                    continue
                kind = CHANGE.MetadataUpdated
                # Do not borrow recurrence evidence across absence/reappearance.
                start = len(members) - 1
                while start > 0 and dataset in members[start - 1]:
                    start -= 1
                pairs = [i for i in range(start + 1, len(observations) - 1)
                         if observations[i][0].date() == yesterday]
                if any(not isomorphic(view(i - 1, dataset), view(i, dataset)) for i in pairs):
                    continue
                covered = any(observations[i][0] - observations[i - 1][0] <= timedelta(hours=36)
                              for i in pairs)
                recurrence = CHANGE.NotObserved if covered else CHANGE.Unknown
            event = identity(activity, dataset, kind)
            graph.add((root, CHANGE.change, event))
            graph.add((event, RDF.type, kind))
            graph.add((event, CHANGE.dataset, dataset))
            graph.add((event, CHANGE.catalog, catalog))
            graph.add((event, CHANGE.previousDayRecurrence, recurrence))
            graph.add((event, PROV.wasGeneratedBy, activity))
            graph.add((event, CHANGE.windowStart, Literal(observations[-2][0], datatype=XSD.dateTime)))
            graph.add((event, CHANGE.windowEnd, Literal(observations[-1][0], datatype=XSD.dateTime)))
            graph.add((dataset, RDF.type, DCAT.Dataset))
            source = graphs[-1] if dataset in after else graphs[-2]
            for title in source.objects(dataset, DCT.title):
                graph.add((dataset, DCT.title, title))
            if kind == CHANGE.MetadataUpdated:
                _, removed, added = graph_diff(to_isomorphic(view(-2, dataset)),
                                                to_isomorphic(view(-1, dataset)))
                # Canonical blank-node labels are local to this dataset diff.
                scoped = {}

                def scope(term):
                    if isinstance(term, BNode):
                        return scoped.setdefault(term, BNode())
                    return term

                for relation, delta in ((CHANGE.removedStatement, removed), (CHANGE.addedStatement, added)):
                    for subject, predicate, obj in delta:
                        subject, obj = scope(subject), scope(obj)
                        statement = BNode()
                        graph.add((event, relation, statement))
                        graph.add((event, CHANGE.changedPredicate, predicate))
                        graph.add((statement, RDF.type, RDF.Statement))
                        graph.add((statement, RDF.subject, subject))
                        graph.add((statement, RDF.predicate, predicate))
                        graph.add((statement, RDF.object, obj))
    return graph


def markdown(graph):
    """Compact view of retained findings; full identities/evidence stay in RDF."""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    rows = []
    for event in graph.subjects(CHANGE.dataset, None):
        dataset = graph.value(event, CHANGE.dataset)
        catalog = graph.value(event, CHANGE.catalog)
        publisher = graph.value(catalog, DCT.publisher)
        dno = str(publisher or catalog).rstrip("/").split("/")[-1]
        if publisher is None and dno == "catalogue":
            dno = str(catalog).rstrip("/").split("/")[-2]
        identifier = str(dataset).rstrip("/").split("/")[-1]
        title = next(iter(sorted(graph.objects(dataset, DCT.title), key=str)), dataset)
        rows.append((dno.upper(), identifier, title))
    lines = ["| DNO | Dataset ID | Dataset name |", "|---|---|---|"]
    lines.extend("| " + " | ".join(map(cell, row)) + " |" for row in sorted(rows, key=lambda r: tuple(map(str, r))))
    lines.append("\nObserved catalogue changes only. Unknown previous-day recurrence is retained; see RDF for event types and evidence.")
    return "\n".join(lines) + "\n"


def load_bucket_archive(env_file):
    """Read and checksum-verify the latest published export, without local fallback."""
    from dotenv import load_dotenv
    from .bucket_store import Settings, client_for, read_remote

    load_dotenv(env_file, override=False)
    settings = Settings.from_env()
    client = client_for(settings)
    index = json.loads(read_remote(client, settings, "exports/latest.json"))
    entry = index["files"]["observations.trig"]
    prefix = settings.uri + "/"
    if not entry["uri"].startswith(prefix):
        raise ValueError("Export URI is outside the configured bucket prefix")
    relative = entry["uri"][len(prefix):]
    parts = relative.split("/")
    if (len(parts) != 3 or parts[0] != "exports" or parts[1] in ("", ".", "..")
            or "\\" in relative or parts[2] != "observations.trig"):
        raise ValueError("Unsafe export path")
    # History exports grow beyond individual capture sizes. Still bound the read.
    body = client.get_object(Bucket=settings.bucket, Key=settings.key(relative))["Body"]
    try:
        content = body.read(512 * 1024 * 1024 + 1)
    finally:
        body.close()
    if len(content) > 512 * 1024 * 1024:
        raise ValueError("Export exceeds 512 MiB limit")
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError("Export SHA-256 mismatch")
    archive = Dataset(default_union=False)
    archive.parse(data=content, format="trig")
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Explicit local TriG export instead of bucket latest")
    parser.add_argument("--env-file", type=Path, default=Path.cwd() / ".env")
    parser.add_argument("--output", type=Path, help="RDF/XML output path (default: stdout)")
    parser.add_argument("--markdown", type=Path, help="Also write a three-column Markdown table")
    args = parser.parse_args(argv)
    try:
        if args.input is not None:
            archive = Dataset(default_union=False)
            archive.parse(args.input, format="trig")
        else:
            archive = load_bucket_archive(args.env_file)
        result = report(archive)
        serialized = result.serialize(format="xml")
        if not isomorphic(result, Graph().parse(data=serialized, format="xml")):
            raise ValueError("RDF/XML round-trip changed report")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
        else:
            print(serialized, end="")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown(result), encoding="utf-8")
        return 0
    except ImportError:
        print("Bucket access requires optional dependencies: install busbar[s3]", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Change report failed: {type(exc).__name__} "
              "(check input, bucket access and export integrity)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
