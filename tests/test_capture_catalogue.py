import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_catalogue as capture

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
        shapes = capture.Graph().parse(
            capture.ROOT / "shapes/publishing.ttl", format="turtle",
        )
        conforms, _, _ = capture.validate(graph, shacl_graph=shapes, inference="none")
        self.assertFalse(conforms)

    def paged_rdf(self, next_page=None, total=2):
        paging = f'<hydra:totalItems>{total}</hydra:totalItems>'
        if next_page:
            paging += f'<hydra:nextPage rdf:resource="{next_page}"/>'
        return RDF.replace(
            b'xmlns:dcat=', b'xmlns:hydra="http://www.w3.org/ns/hydra/core#" xmlns:dcat=',
        ).replace(
            b'<dcat:Catalog rdf:about="https://source.example/catalog"/>',
            ('<dcat:Catalog rdf:about="https://source.example/catalog">'
             + paging + '</dcat:Catalog>').encode(),
        )

    def test_paginated_capture_preserves_pages_and_combines_membership(self):
        first = self.paged_rdf('https://frontend.example/catalog.rdf?page=2')
        second = self.paged_rdf().replace(b'datasets/one', b'datasets/two')
        spec = capture.DEFAULT_SPEC.replace('/ukpn/', '/nged/')
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, 'urlopen', side_effect=[Response(first), Response(second)]) as mocked:
                record, _ = capture.capture(self.graph, self.hashes, spec, Path(output))
            self.assertEqual(record['status'], 'success')
            self.assertEqual(record['dataset_count'], 2)
            self.assertEqual(record['artifact_kind'], 'rdf-page-union')
            self.assertEqual(mocked.call_args_list[1].args[0].full_url,
                             'https://connecteddata.nationalgrid.co.uk/catalog.rdf?page=2')
            for page, original in zip(record['pages'], [first, second]):
                self.assertEqual((Path(output) / page['artifact_path']).read_bytes(), original)
            self.assertEqual(len(capture.parse_catalogue(
                (Path(output) / record['artifact_path']).read_bytes())[0]), 2)
            with patch.object(capture, 'urlopen', side_effect=[Response(first), Response(second)]):
                repeated, _ = capture.capture(self.graph, self.hashes, spec, Path(output))
            self.assertFalse(repeated['comparison']['bytes_changed'])
            self.assertEqual(repeated['comparison']['newly_listed'], [])

    def test_failed_second_page_does_not_create_successful_partial_catalogue(self):
        first = self.paged_rdf('https://source.example/catalog.rdf?page=2')
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, 'urlopen', side_effect=[Response(first), URLError('offline')]):
                record, _ = self.run_capture(output)
            self.assertEqual(record['status'], 'failed')
            self.assertNotIn('dataset_count', record)
            self.assertIsNone(capture.previous_success(Path(output), capture.DEFAULT_SPEC))
            self.assertEqual((Path(output) / record['pages'][0]['artifact_path']).read_bytes(), first)

    def test_pagination_cycle_is_rejected(self):
        page = self.paged_rdf('https://source.example/catalog.rdf?page=1')
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, 'urlopen', return_value=Response(page)) as mocked:
                record, _ = self.run_capture(output)
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(mocked.call_count, 1)

    def test_incomplete_catalogue_is_rejected(self):
        with tempfile.TemporaryDirectory() as output:
            with patch.object(capture, 'urlopen', return_value=Response(self.paged_rdf())):
                record, _ = self.run_capture(output)
            self.assertEqual(record['status'], 'failed')
            self.assertNotIn('dataset_count', record)

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
