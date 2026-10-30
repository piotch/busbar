import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from busbar import capture_catalogue as capture

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dcat="http://www.w3.org/ns/dcat#">
  <dcat:Catalog rdf:about="https://source.example/catalog"/>
  <dcat:Dataset rdf:about="https://source.example/datasets/one"/>
</rdf:RDF>"""


class Response:
    status = 200
    url = "https://source.example/export"
    headers = {"Content-Type": "application/rdf+xml"}

    def __init__(self, content=RDF):
        self.content = content

    def read(self, limit):
        return self.content[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.hashes = capture.load_declarations()

    def run_capture(self, output):
        with patch.object(capture, "git_revision", return_value="test"):
            return capture.capture(
                self.graph, self.hashes, capture.DEFAULT_SPEC, Path(output),
            )

    def test_declarations_resolve(self):
        catalog, endpoint, media_type = capture.capture_parameters(
            self.graph, capture.DEFAULT_SPEC,
        )
        self.assertTrue(catalog.endswith("/catalogue"))
        self.assertTrue(endpoint.startswith("https://"))
        self.assertEqual(media_type, "application/rdf+xml")

    def test_missing_portal_operator_fails_validation(self):
        graph = capture.Graph()
        for triple in self.graph:
            graph.add(triple)
        graph.remove((None, capture.PUB.portalOperator, None))
        shapes = capture.load_graph("shapes/publishing.ttl")
        conforms, _, _ = capture.validate(graph, shacl_graph=shapes, inference="none")
        self.assertFalse(conforms)

    def test_unknown_spec_rejected(self):
        with self.assertRaises(ValueError):
            capture.capture_parameters(self.graph, "https://unknown.example/spec")

    def test_unchanged_capture_deduplicates_bytes_but_records_observation(self):
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, "urlopen", side_effect=[Response(), Response()]):
                first, _ = self.run_capture(output)
                second, _ = self.run_capture(output)
            self.assertEqual(first["status"], "success")
            self.assertEqual(first["dataset_count"], 1)
            self.assertFalse(second["comparison"]["bytes_changed"])
            self.assertEqual(second["comparison"]["no_longer_listed"], [])
            self.assertEqual(len(list(Path(output).glob("objects/sha256/*.rdf"))), 1)
            self.assertEqual(len(list(Path(output).glob("observations/*.json"))), 2)

    def test_failure_is_not_catalogue_disappearance(self):
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, "urlopen", return_value=Response()):
                first, _ = self.run_capture(output)
            with patch.object(capture, "urlopen", side_effect=URLError("offline")):
                failed, path = self.run_capture(output)
            self.assertEqual(failed["status"], "failed")
            self.assertNotIn("comparison", failed)
            self.assertNotIn("dataset_count", failed)
            self.assertEqual(json.loads(path.read_text())["status"], "failed")
            previous = capture.previous_success(Path(output), capture.DEFAULT_SPEC)
            self.assertEqual(previous["observation_id"], first["observation_id"])

    def test_parse_failure_preserves_original_response(self):
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, "urlopen", return_value=Response(b"<html>error</html>")):
                record, _ = self.run_capture(output)
            self.assertEqual(record["status"], "failed")
            self.assertIn("artifact_uri", record)
            self.assertNotIn("comparison", record)

    def test_membership_change_does_not_claim_deletion(self):
        empty = RDF.replace(
            b'<dcat:Dataset rdf:about="https://source.example/datasets/one"/>', b"",
        )
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, "urlopen", side_effect=[Response(), Response(empty)]):
                self.run_capture(output)
                second, _ = self.run_capture(output)
            self.assertEqual(second["comparison"]["no_longer_listed"],
                             ["https://source.example/datasets/one"])

    def test_rdf_without_catalog_is_rejected(self):
        content = RDF.replace(
            b'<dcat:Catalog rdf:about="https://source.example/catalog"/>', b"",
        )
        with self.assertRaises(ValueError):
            capture.parse_catalogue(content)


if __name__ == "__main__":
    unittest.main()
