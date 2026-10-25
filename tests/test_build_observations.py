import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_observations as export
from capture_catalogue import DEFAULT_SPEC
from rdflib import BNode, Dataset, Literal, RDF, URIRef
from rdflib.compare import isomorphic

RDF_XML = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:dcat="http://www.w3.org/ns/dcat#" xmlns:dct="http://purl.org/dc/terms/">
 <dcat:Catalog rdf:about="https://source.example/catalog">
   <dcat:dataset rdf:resource="https://source.example/dataset/one"/>
   <dct:publisher><rdf:Description><dct:title>Publisher</dct:title></rdf:Description></dct:publisher>
 </dcat:Catalog>
 <dcat:Dataset rdf:about="https://source.example/dataset/one"/>
</rdf:RDF>'''


class ObservationExportTests(unittest.TestCase):
    def write(self, directory, identifier, status="success", content=RDF_XML):
        artifact = directory / (identifier + ".rdf")
        artifact.write_bytes(content)
        record = {
            "observation_id": identifier,
            "catalog": DEFAULT_SPEC.rsplit('/captures/', 1)[0],
            "specification": DEFAULT_SPEC,
            "observed_at": "2026-10-24T10:00:00+00:00",
            "status": status,
            "artifact_uri": artifact.as_uri(),
            "content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
            "dataset_count": 1,
        }
        path = directory / (identifier + ".json")
        path.write_text(json.dumps(record))
        return path

    def test_identical_captures_stay_separate_and_blank_nodes_are_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, summary = export.build([self.write(root, "a"), self.write(root, "b")])
            snapshots = [dataset.graph(URIRef(identifier)) for identifier, _, _ in summary]
            self.assertEqual(len(snapshots), 2)
            busbar = URIRef('https://busbar.example/id/grid/catalogues/busbar')
            curated = dataset.graph(export.CURATED)
            self.assertEqual(len(set(curated.objects(busbar, export.DCAT.dataset))), 96)
            self.assertNotIn((busbar, export.DCAT.dataset, None), dataset.graph(export.DEFINITIONS))
            for snapshot in snapshots:
                self.assertNotIn((busbar, None, None), snapshot)
                self.assertNotIn((None, RDF.type, export.DCAT.DatasetSeries), snapshot)
            self.assertTrue(isomorphic(*snapshots))
            blank_sets = [{term for triple in graph for term in triple if isinstance(term, BNode)}
                          for graph in snapshots]
            self.assertTrue(blank_sets[0])
            self.assertFalse(blank_sets[0] & blank_sets[1])
            self.assertEqual(len(list(dataset.query('SELECT * WHERE { ?s ?p ?o }'))), 0)
            for graph in snapshots:
                self.assertIn((URIRef('https://source.example/catalog'), RDF.type, export.DCAT.Catalog), graph)
                self.assertNotIn((None, export.PUB.observedCatalog, None), graph)
            path = root / "export.trig"
            dataset.serialize(destination=str(path), format="trig")
            reloaded = Dataset(default_union=False).parse(path, format="trig")
            for identifier, _, _ in summary:
                self.assertTrue(isomorphic(dataset.graph(URIRef(identifier)), reloaded.graph(URIRef(identifier))))

    def test_sparql_queries_observations_and_membership_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = self.write(root, 'before')
            after = self.write(root, 'after', content=RDF_XML.replace(b'/dataset/one', b'/dataset/two'))
            dataset, summary = export.build([before, after])
        metadata = dataset.graph(export.METADATA)
        by_id = {str(node).rsplit('/', 1)[-1]: node
                 for node in metadata.subjects(RDF.type, export.PUB.CatalogSnapshot)}
        query_dir = export.ROOT / 'queries'
        observations = list(dataset.query((query_dir / 'list-observations.rq').read_text()))
        self.assertEqual(len(observations), 2)
        added = list(dataset.query((query_dir / 'newly-listed-datasets.rq').read_text(),
                                  initBindings={'before': by_id['before'], 'after': by_id['after']}))
        self.assertEqual([row.dataset for row in added], [URIRef('https://source.example/dataset/two')])

    def test_failed_observation_has_metadata_but_no_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, summary = export.build([self.write(Path(directory), "failed", "failed", b"not RDF")])
            observation = URIRef(summary[0][0])
            self.assertEqual(len(dataset.graph(observation)), 0)
            metadata = dataset.graph(export.METADATA)
            self.assertIn((observation, export.PUB.status, Literal("failed")), metadata)
            self.assertNotIn((observation, RDF.type, export.PUB.CatalogSnapshot), metadata)

    def test_tampered_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write(root, "a")
            (root / "a.rdf").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                export.build([path])

    def test_duplicate_observation_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), "a")
            with self.assertRaisesRegex(ValueError, 'Duplicate observation'):
                export.build([path, path])

    def test_empty_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No observations'):
            export.build([])


if __name__ == '__main__':
    unittest.main()
