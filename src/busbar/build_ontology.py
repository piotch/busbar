"""Build a news/source ontology with one selected catalogue capture per source."""
import argparse
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, XSD

from .capture_catalogue import capture_parameters, load_declarations
from .artifact_store import artifact_bytes, manifest_reference

DCT = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PUB = Namespace("https://busbar.example/publishing#")
PROV = Namespace("http://www.w3.org/ns/prov#")


def select_observation(directory, specification):
    candidates = []
    for path in directory.glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("status") == "success" and record.get("specification") == specification:
            candidates.append((record["observed_at"], path, record))
    if not candidates:
        raise ValueError(f"No successful capture for {specification}. Run busbar capture --spec '{specification}' first.")
    _, path, record = max(candidates, key=lambda item: item[0])
    return path, record


def build(observation_path):
    record = json.loads(observation_path.read_text())
    if record.get("status") != "success":
        raise ValueError("Expected a successful catalogue observation")
    graph, _ = load_declarations()
    expected_catalog, _, _ = capture_parameters(graph, record.get("specification", ""))
    if record.get("catalog") != expected_catalog:
        raise ValueError("Observation catalogue does not match its declared specification")
    content = artifact_bytes(record, observation_path)

    # Only the new source registry is loaded: never busbar-ontology.ttl/catalogue.ttl.
    captured = Graph().parse(data=content, format="xml")
    source_catalogs = set(captured.subjects(RDF.type, DCAT.Catalog))
    if len(source_catalogs) != 1:
        raise ValueError("Expected exactly one source catalogue; refusing an ambiguous identity merge")
    if len(set(captured.subjects(RDF.type, DCAT.Dataset))) != record["dataset_count"]:
        raise ValueError("Captured dataset count does not match the observation")
    # Canonicalize only in this derived view; the archived bytes stay untouched.
    catalog = URIRef(record["catalog"])
    source = next(iter(source_catalogs))
    for subject, predicate, obj in captured:
        if subject == source and predicate in (DCT.title, RDFS.label):
            # Keep the curated catalogue name unambiguous in Protégé.
            graph.add((catalog, PUB.sourceCatalogTitle, obj))
            continue
        graph.add((catalog if subject == source else subject, predicate,
                   catalog if obj == source else obj))
    graph.add((catalog, PUB.sourceCatalogIdentifier, Literal(str(source), datatype=XSD.anyURI)))
    snapshot = URIRef(str(catalog) + "/observations/" + record["observation_id"])
    graph.add((snapshot, RDF.type, PUB.CatalogSnapshot))
    graph.add((snapshot, RDFS.label, Literal(str(next(graph.objects(catalog, DCT.title), catalog)) + " observed " + record["observed_at"])))
    graph.add((snapshot, PUB.observedCatalog, catalog))
    graph.add((snapshot, PROV.generatedAtTime, Literal(record["observed_at"], datatype=XSD.dateTime)))
    graph.add((snapshot, PROV.wasDerivedFrom, URIRef(record["artifact_uri"])))
    graph.add((snapshot, PROV.hadPrimarySource, URIRef(record["artifact_uri"])))

    # Readable graph-node labels are a viewer convenience, not publisher assertions.
    for subject, title in list(graph.subject_objects(DCT.title)):
        if isinstance(title, Literal) and not any(graph.objects(subject, RDFS.label)):
            graph.add((subject, RDFS.label, title))
    for header in list(graph.subjects(RDF.type, OWL.Ontology)):
        graph.remove((header, None, None))
    document = URIRef("https://busbar.example/ontology/news-catalogues")
    graph.add((document, RDF.type, OWL.Ontology))
    graph.add((document, DCT.title, Literal("News sources — captured DNO catalogues", lang="en")))
    graph.add((document, DCT.description, Literal(
        "Viewer projection of independent news/source declarations and selected DNO DCAT captures. "
        "No original Busbar grid ontology or curated catalogue is included. "
        "Catalogue identity normalization, source-identity metadata, capture provenance and readable labels are derived additions. "
        "Source declarations reflect the current Git files; captured publisher metadata reflects the observation time.",
        lang="en",
    )))
    graph.add((document, PROV.wasDerivedFrom, URIRef(manifest_reference(record, observation_path))))
    return graph, record


def build_many(observation_paths):
    graph = Graph()
    records = []
    specifications = set()
    for path in observation_paths:
        part, record = build(path)
        if record["specification"] in specifications:
            raise ValueError("Select only one observation per specification; mixing historical states would conflate catalogue membership")
        specifications.add(record["specification"])
        graph += part
        records.append(record)
    if not records:
        raise ValueError("Select at least one observation")
    return graph, records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.cwd() / "build/news-catalogues.owl")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--observation", type=Path, action="append", help="Successful observation JSON; repeat for multiple sources")
    selection.add_argument("--spec", action="append", help="Specification IRI; repeat to select sources (default: all declared)")
    parser.add_argument("--captures", type=Path, default=Path.cwd() / "captures")
    args = parser.parse_args(argv)
    paths = args.observation
    if paths is None:
        declarations, _ = load_declarations()
        specifications = args.spec or sorted(map(str, declarations.subjects(RDF.type, PUB.CaptureSpecification)))
        paths = [select_observation(args.captures / "observations", spec)[0] for spec in specifications]
    graph, records = build_many(paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(args.output), format="xml")
    result = Graph().parse(args.output, format="xml")
    if len(result) != len(graph):
        raise ValueError("Export round-trip changed the triple count")
    print(f"Built {args.output.resolve()} ({len(graph)} triples; {len(records)} captures)")
    for record, path in zip(records, paths):
        print(f"  {record['catalog']}: {record['dataset_count']} datasets ({path.name})")


if __name__ == "__main__":
    main()
