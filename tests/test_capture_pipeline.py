import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import artifact_store
import build_observations
import build_ontology
import capture_all
import capture_catalogue as capture
from rdflib import URIRef

RDF_XML = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:dcat="http://www.w3.org/ns/dcat#">
 <dcat:Catalog rdf:about="https://source.example/catalog">
   <dcat:dataset rdf:resource="https://source.example/dataset"/>
 </dcat:Catalog>
 <dcat:Dataset rdf:about="https://source.example/dataset"/>
</rdf:RDF>'''


class Response:
    status = 200
    url = "https://source.example/export"
    headers = {"Content-Type": "application/rdf+xml"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return RDF_XML


class CapturePipelineTests(unittest.TestCase):
    def test_portable_capture_can_be_restored_on_another_machine(self):
        graph, hashes = capture.load_declarations()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(capture, "urlopen", return_value=Response()):
                record, path = capture.capture(graph, hashes, capture.DEFAULT_SPEC,
                                               root / "runner-one", "s3://busbar/catalogue-history")
            self.assertTrue(record["artifact_uri"].startswith("s3://"))
            self.assertTrue(record["manifest_uri"].startswith("s3://"))
            shutil.copytree(root / "runner-one", root / "runner-two")
            restored = root / "runner-two/observations" / path.name
            shutil.rmtree(root / "runner-one")
            self.assertEqual(artifact_store.artifact_bytes(record, restored), RDF_XML)
            viewer, _ = build_ontology.build(restored)
            history, _ = build_observations.build([restored])
            for graph in [viewer, *history.graphs()]:
                self.assertFalse(any(str(term).startswith("file://") for triple in graph for term in triple))
            metadata = history.graph(build_observations.METADATA)
            self.assertIn((None, build_observations.PROV.wasDerivedFrom, URIRef(record["manifest_uri"])), metadata)

    def test_artifact_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "artifact path"):
            artifact_store.artifact_bytes({"artifact_path": "../private.env"}, Path("observations/a.json"))

    def test_provider_failure_does_not_skip_other_sources(self):
        def mock_capture(graph, hashes, specification, output, storage_uri):
            if "/npg/" in specification:
                raise RuntimeError("source failed")
            return {"status": "success", "dataset_count": 136}, output / "observations/a.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(capture_all, "capture", side_effect=mock_capture) as mocked:
                results = capture_all.run(root / "captures", root / "summary.json")
            self.assertEqual(mocked.call_count, 6)
            self.assertEqual(len({r["specification"] for r in results}), 6)
            self.assertEqual({r["status"] for r in results}, {"success", "failed"})
            self.assertEqual(len(json.loads((root / "summary.json").read_text())["sources"]), 6)


if __name__ == "__main__":
    unittest.main()
