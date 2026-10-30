import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from capture_catalogue import ROOT, load_declarations
from rdflib import Graph, Namespace, RDF, URIRef
from pyshacl import validate

ORG = Namespace("http://www.w3.org/ns/org#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
DCT = Namespace("http://purl.org/dc/terms/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
GRID = Namespace("https://busbar.example/grid#")
PUB = Namespace("https://busbar.example/publishing#")
BASE = "https://busbar.example/id/"
BUSBAR = URIRef(BASE + "grid/catalogues/busbar")
REFERENCEWORKS = URIRef(BASE + "organisations/referenceworks")


class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definitions, _ = load_declarations()
        cls.curated = Graph().parse(ROOT / "catalogue.ttl", format="turtle")
        cls.domain = Graph().parse(ROOT / "busbar-ontology.ttl", format="turtle")

    def test_referenceworks_publishes_and_maintains_busbar(self):
        self.assertIn((REFERENCEWORKS, RDF.type, ORG.Organization), self.definitions)
        self.assertIn((BUSBAR, RDF.type, DCAT.Catalog), self.definitions)
        self.assertIn((BUSBAR, DCT.publisher, REFERENCEWORKS), self.definitions)
        self.assertIn((BUSBAR, PUB.maintainedBy, REFERENCEWORKS), self.definitions)
        self.assertNotIn((BUSBAR, RDF.type, PUB.TrackedCatalog), self.definitions)
        self.assertNotIn((None, PUB.catalog, BUSBAR), self.definitions)

    def test_dno_is_a_domain_classification_not_a_publishing_class(self):
        self.assertIn((GRID.DistributionNetworkOperator, RDF.type, SKOS.Concept), self.definitions)
        self.assertNotIn((PUB.DistributionNetworkOperator, None, None), self.definitions)
        for dno in ("ukpn", "npg", "spen", "ssen", "nged", "enwl"):
            organization = URIRef(BASE + "grid/uk/dno/" + dno)
            catalog = URIRef(str(organization) + "/catalogue")
            self.assertIn((organization, RDF.type, ORG.Organization), self.definitions)
            self.assertIn((organization, ORG.classification, GRID.DistributionNetworkOperator), self.definitions)
            self.assertIn((catalog, DCT.publisher, organization), self.definitions)
            self.assertNotIn((catalog, PUB.maintainedBy, REFERENCEWORKS), self.definitions)

    def test_all_six_dnos_have_portals_and_capture_specifications(self):
        expected = {URIRef(BASE + 'grid/uk/dno/' + dno)
                    for dno in ('ukpn', 'npg', 'spen', 'ssen', 'nged', 'enwl')}
        self.assertEqual(set(self.definitions.subjects(
            ORG.classification, GRID.DistributionNetworkOperator)), expected)
        self.assertEqual(set(self.definitions.subjects(RDF.type, PUB.CaptureSpecification)),
                         {URIRef(str(org) + '/catalogue/captures/dcat') for org in expected})
        for organization in expected:
            portal = URIRef(str(organization) + '/portal')
            catalog = URIRef(str(organization) + '/catalogue')
            spec = URIRef(str(catalog) + '/captures/dcat')
            self.assertIn((portal, PUB.portalOperator, organization), self.definitions)
            self.assertIn((portal, PUB.exposesCatalog, catalog), self.definitions)
            self.assertIn((spec, PUB.catalog, catalog), self.definitions)

    def test_curated_and_domain_graphs_reuse_the_shared_organization_ids(self):
        self.assertEqual(len(set(self.curated.objects(BUSBAR, DCAT.dataset))), 96)
        self.assertEqual(len(set(self.curated.subjects(RDF.type, DCAT.Dataset))), 220)
        for old, dno in ((name.upper(), name) for name in ("ukpn", "npg", "spen", "ssen", "nged", "enwl")):
            organization = URIRef(BASE + "grid/uk/dno/" + dno)
            self.assertTrue(any(self.curated.subjects(DCT.publisher, organization)))
            self.assertIn((organization, None, None), self.domain)
            for graph in (self.definitions, self.curated, self.domain):
                self.assertNotIn((URIRef(BASE + old), None, None), graph)
                self.assertNotIn((None, None, URIRef(BASE + old)), graph)
        self.assertNotIn((URIRef(BASE + "busbar"), None, None), self.curated)

    def test_no_catalogue_owned_dno_classes_remain(self):
        old_class = URIRef('https://busbar.example/ns#DistributionNetworkOperator')
        for graph in (self.definitions, self.domain, self.curated):
            for obsolete in (old_class, PUB.DistributionNetworkOperator):
                self.assertNotIn((obsolete, None, None), graph)
                self.assertNotIn((None, None, obsolete), graph)
        operators = set(self.domain.subjects(ORG.classification, GRID.DistributionNetworkOperator))
        self.assertEqual(len(operators), 6)
        for operator in operators:
            self.assertIn((operator, RDF.type, ORG.Organization), self.domain)

    def test_dno_definition_has_a_versioned_glossary_citation(self):
        concept = GRID.DistributionNetworkOperator
        definition = self.definitions.value(concept, SKOS.definition)
        self.assertEqual(str(definition),
                         'A DNO is a company that owns, operates and maintains an electric distribution network in Great Britain.')
        self.assertEqual(definition.language, 'en')
        source = self.definitions.value(concept, DCT.source)
        self.assertEqual(str(source), BASE + 'references/ltds-grid-modelling-v2-1-1/annex-2-v7')
        self.assertIn((source, RDF.type, URIRef('http://xmlns.com/foaf/0.1/Document')), self.definitions)
        citation = str(self.definitions.value(source, DCT.bibliographicCitation))
        self.assertIn('section 6', citation)
        self.assertIn('page 75', citation)
        self.assertIn((source, DCT.isPartOf,
                       URIRef('https://cim.bsigroup.com/releases/ltds/ltds-grid-modelling-v2-1-1-r15/')),
                      self.definitions)
        self.assertNotIn((concept, SKOS.exactMatch, None), self.definitions)
        self.assertNotIn((concept, URIRef('http://www.w3.org/2002/07/owl#equivalentClass'), None), self.definitions)

    def test_missing_curator_is_invalid(self):
        graph = Graph()
        for triple in self.definitions:
            graph.add(triple)
        graph.remove((BUSBAR, PUB.maintainedBy, None))
        shapes = Graph().parse(ROOT / "shapes/publishing.ttl", format="turtle")
        conforms, _, _ = validate(graph, shacl_graph=shapes, inference="none")
        self.assertFalse(conforms)


if __name__ == "__main__":
    unittest.main()
