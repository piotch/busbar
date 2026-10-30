import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_ontology as builder
import capture_catalogue as capture

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dcat="http://www.w3.org/ns/dcat#"
         xmlns:dct="http://purl.org/dc/terms/">
  <dcat:Catalog rdf:about="https://source.example/catalog">
    <dct:title>Publisher catalogue title</dct:title>
    <dcat:dataset rdf:resource="https://source.example/datasets/one"/>
  </dcat:Catalog>
  <dcat:Dataset rdf:about="https://source.example/datasets/one">
    <dct:isPartOf rdf:resource="https://source.example/catalog"/>
  </dcat:Dataset>
</rdf:RDF>"""


class BuilderTests(unittest.TestCase):
    def write_observation(self, directory, specification=capture.DEFAULT_SPEC, content=RDF):
        directory.mkdir(parents=True, exist_ok=True)
        artifact = directory / "capture.rdf"
        artifact.write_bytes(content)
        record = {
            "status": "success", "specification": specification,
            "artifact_uri": artifact.as_uri(),
            "content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
            "catalog": capture.capture_parameters(capture.load_declarations()[0],
                                                  specification)[0],
            "observation_id": "test-observation",
            "observed_at": "2026-10-24T10:00:00+00:00",
            "dataset_count": 1,
        }
        path = directory / "observation.json"
        path.write_text(json.dumps(record))
        return path

    def test_independent_export_contains_captured_catalogue_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_observation(Path(directory))
            graph, record = builder.build(path)
            self.assertEqual((Path(directory) / "capture.rdf").read_bytes(), RDF)
        forbidden = "https://busbar.example/ns#"
        for triple in graph:
            self.assertFalse(any(str(term).startswith(forbidden) for term in triple))
        self.assertNotIn((builder.URIRef("https://busbar.example/id/UKPN"), None, None), graph)
        self.assertEqual(len(list(graph.subjects(builder.RDF.type, builder.OWL.Ontology))), 1)
        self.assertEqual(len(list(graph.subjects(builder.RDF.type, builder.DCAT.Dataset))), 1)
        self.assertEqual(len(list(graph.subjects(builder.RDF.type, builder.PUB.CatalogSnapshot))), 1)
        catalog = builder.URIRef(record["catalog"])
        source = builder.URIRef("https://source.example/catalog")
        dataset = builder.URIRef("https://source.example/datasets/one")
        self.assertIn(catalog, set(graph.subjects(builder.RDF.type, builder.DCAT.Catalog)))
        self.assertNotIn(source, set(graph.subjects(builder.RDF.type, builder.DCAT.Catalog)))
        self.assertIn((catalog, builder.DCAT.dataset, dataset), graph)
        self.assertIn((dataset, builder.DCT.isPartOf, catalog), graph)
        self.assertNotIn((source, None, None), graph)
        self.assertNotIn((None, None, source), graph)
        self.assertIn((catalog, builder.PUB.sourceCatalogIdentifier,
                       builder.Literal(str(source), datatype=builder.XSD.anyURI)), graph)
        self.assertIn((catalog, builder.PUB.sourceCatalogTitle,
                       builder.Literal("Publisher catalogue title")), graph)
        self.assertNotIn((catalog, builder.RDFS.label,
                          builder.Literal("Publisher catalogue title")), graph)

    def test_combined_export_keeps_source_membership_separate(self):
        npg_spec = capture.DEFAULT_SPEC.replace('/ukpn/', '/npg/')
        npg_content = RDF.replace(b'source.example', b'npg.example')
        with tempfile.TemporaryDirectory() as directory:
            first = self.write_observation(Path(directory) / 'ukpn')
            second = self.write_observation(Path(directory) / 'npg', npg_spec, npg_content)
            graph, records = builder.build_many([first, second])
        catalogs = set(graph.subjects(builder.RDF.type, builder.DCAT.Catalog))
        declarations, _ = capture.load_declarations()
        self.assertEqual(catalogs, set(declarations.subjects(builder.RDF.type, builder.DCAT.Catalog)))
        for record, domain in zip(records, ['source.example', 'npg.example']):
            members = set(graph.objects(builder.URIRef(record['catalog']), builder.DCAT.dataset))
            self.assertEqual(members, {builder.URIRef(f'https://{domain}/datasets/one')})
        self.assertEqual(len(list(graph.subjects(builder.RDF.type, builder.PUB.CatalogSnapshot))), 2)
        self.assertEqual(len(list(graph.subjects(builder.RDF.type, builder.OWL.Ontology))), 1)

    def test_two_states_of_same_source_are_not_flattened_together(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_observation(Path(directory))
            with self.assertRaisesRegex(ValueError, 'one observation per specification'):
                builder.build_many([path, path])

    def test_wrong_catalogue_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_observation(Path(directory))
            record = json.loads(path.read_text())
            record['catalog'] = 'https://wrong.example/catalog'
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                builder.build(path)

    def test_artifact_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_observation(Path(directory))
            (Path(directory) / "capture.rdf").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                builder.build(path)

    def test_failed_observation_is_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_observation(Path(directory))
            failed = json.loads(path.read_text())
            failed.update(status="failed", observed_at="2099-01-01T00:00:00+00:00")
            (Path(directory) / "failed.json").write_text(json.dumps(failed))
            selected, _ = builder.select_observation(Path(directory), capture.DEFAULT_SPEC)
            self.assertEqual(selected, path)


if __name__ == "__main__":
    unittest.main()
