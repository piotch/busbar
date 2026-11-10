"""Build a deterministic, provenance-preserving projection of the local RDF.

Run from any directory: .venv/bin/python visualisation/export_graph.py
Includes recorded edition metadata, but not remote vocabularies or catalogue snapshots.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, SKOS, DCTERMS, FOAF

ROOT = Path(__file__).resolve().parents[1]
DCAT = Namespace('http://www.w3.org/ns/dcat#')
ORG = Namespace('http://www.w3.org/ns/org#')
PUB = Namespace('https://busbar.example/publishing#')
PREFIXES = {
    'busbar': 'https://busbar.example/ns#', 'grid': 'https://busbar.example/grid#',
    'pub': str(PUB), 'id': 'https://busbar.example/id/', 'dcat': str(DCAT),
    'org': str(ORG), 'skos': str(SKOS), 'owl': str(OWL), 'rdf': str(RDF),
    'rdfs': str(RDFS), 'dct': str(DCTERMS), 'foaf': str(FOAF),
    'prov': 'http://www.w3.org/ns/prov#',
}
LAYERS = [
    {'id': 'standards', 'title': 'Shared standards', 'subtitle': 'Local declarations · not complete external ontologies', 'color': '#939182'},
    {'id': 'identities', 'title': 'Organizations & identities', 'subtitle': 'Publishers, operators and shared responsibility', 'color': '#9b7a54'},
    {'id': 'grid', 'title': 'Grid domain', 'subtitle': 'Network classes, project concepts and classifications', 'color': '#64826c'},
    {'id': 'publishing', 'title': 'Publishing vocabulary', 'subtitle': 'Portals, capture specifications and observation classes', 'color': '#65898c'},
    {'id': 'sources', 'title': 'Source infrastructure', 'subtitle': 'Curated declarations · not live catalogue observations', 'color': '#7b789a'},
    {'id': 'catalogue', 'title': 'Curated catalogue', 'subtitle': 'Busbar, series declarations and original catalogue records', 'color': '#ae735e'},
    {'id': 'editions', 'title': 'Recorded editions', 'subtitle': 'Capture-generated edition and file metadata · separate from declarations', 'color': '#a58c53'},
]


def compact(term):
    value = str(term)
    for prefix, base in PREFIXES.items():
        if value.startswith(base):
            return f'{prefix}:{value[len(base):]}'
    return value


def build():
    graph = Graph()
    origins = defaultdict(set)
    triple_origins = defaultdict(set)
    paths = [ROOT / 'busbar-ontology.ttl', ROOT / 'catalogue.ttl']
    paths += sorted((ROOT / 'vocabulary').glob('*.ttl'))
    paths += sorted((ROOT / 'definitions').rglob('*.ttl'))
    paths += sorted((ROOT / 'editions').rglob('*.ttl'))
    for path in paths:
        part = to_canonical_graph(Graph().parse(path, format='turtle'))
        name = path.relative_to(ROOT).as_posix()
        for triple in part:
            graph.add(triple)
            origins[triple[0]].add(name)
            triple_origins[triple].add(name)

    def layer_for(subject):
        value = str(subject)
        types = set(graph.objects(subject, RDF.type))
        if value.startswith(tuple(base for prefix, base in PREFIXES.items()
                                  if prefix not in {'id', 'grid', 'pub', 'busbar'})):
            return 'standards'
        if ORG.Organization in types or FOAF.Organization in types or any(
                str(t).endswith(('#Organisation', '#NetworkOperator', '#SystemOperator', '#TransmissionOwner')) for t in types):
            return 'identities'
        if value.startswith(str(PUB)):
            return 'publishing'
        # A series keeps one identity across its declaration and generated metadata.
        # Only recorded editions/distributions move into the capture-results layer.
        if DCAT.DatasetSeries in types or PUB.CuratedCatalog in types:
            return 'catalogue'
        if any(p.startswith('editions/') for p in origins[subject]):
            return 'editions'
        if 'catalogue.ttl' in origins[subject]:
            return 'catalogue'
        if any(p.startswith('definitions/') for p in origins[subject]):
            return 'sources'
        return 'grid'

    # Include named schema terms/entities and anonymous DCAT distributions,
    # but not restrictions or arbitrary external endpoint URLs.
    # Per-file canonical blank-node IDs keep the generated projection stable.
    property_types = {RDF.Property, OWL.ObjectProperty, OWL.DatatypeProperty,
                      OWL.AnnotationProperty, OWL.TransitiveProperty,
                      OWL.FunctionalProperty, OWL.InverseFunctionalProperty,
                      OWL.SymmetricProperty}
    excluded_types = {OWL.Ontology}
    subjects = set()
    for subject in set(graph.subjects()):
        types = set(graph.objects(subject, RDF.type))
        if not isinstance(subject, URIRef) and not (isinstance(subject, BNode) and DCAT.Distribution in types):
            continue
        if types and not types.intersection(excluded_types):
            subjects.add(subject)

    def first_text(subject, predicates):
        for predicate in predicates:
            values = sorted(graph.objects(subject, predicate), key=str)
            preferred = [v for v in values if isinstance(v, Literal) and v.language in ('en', None)]
            if preferred:
                return str(preferred[0])
        return ''

    def kind_for(types):
        if set(types).intersection(property_types):
            return 'property'
        if OWL.Class in types or RDFS.Class in types or RDFS.Datatype in types:
            return 'class'
        if SKOS.Concept in types:
            return 'concept'
        if SKOS.ConceptScheme in types:
            return 'scheme'
        return 'entity'

    nodes = []
    for subject in sorted(subjects, key=str):
        types = sorted(graph.objects(subject, RDF.type), key=str)
        label = first_text(subject, [SKOS.prefLabel, RDFS.label, DCTERMS.title, FOAF.name])
        if not label and isinstance(subject, BNode):
            url = next(graph.objects(subject, DCAT.downloadURL), None)
            label = str(url).rsplit('/', 1)[-1].split('?', 1)[0] if url else 'Distribution'
        label = label or compact(subject).split(':', 1)[-1]
        nodes.append({
            'id': str(subject), 'short': compact(subject), 'label': label,
            'layer': layer_for(subject), 'types': [compact(t) for t in types],
            'kind': kind_for(types),
            'detail': bool({DCAT.Dataset, DCAT.Distribution}.intersection(types)) and layer_for(subject) != 'editions',
            'description': first_text(subject, [SKOS.definition, RDFS.comment, DCTERMS.description]),
            'sources': sorted(origins[subject]),
        })
    links = []
    for s, p, o in sorted(graph, key=lambda triple: tuple(map(str, triple))):
        if s in subjects and o in subjects:
            links.append({'source': str(s), 'target': str(o), 'predicate': compact(p),
                          'sources': sorted(triple_origins[(s, p, o)])})
    return {'layers': LAYERS, 'nodes': nodes, 'links': links,
            'files': [p.relative_to(ROOT).as_posix() for p in paths],
            'inputs': [{'path': p.relative_to(ROOT).as_posix(),
                        'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}


if __name__ == '__main__':
    data = build()
    output = Path(__file__).with_name('graph.json')
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'{output}: {len(data["nodes"])} nodes, {len(data["links"])} asserted links')
