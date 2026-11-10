import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from busbar import capture_series as capture
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic

SERIES = URIRef("https://busbar.example/id/grid/uk/dno/enwl/series/ecr")
EDITIONS = "https://busbar.example/id/grid/uk/dno/enwl/editions/ecr"
HEADER_ONLY = "﻿Name;Capacity\n".encode()
FIRST = "﻿Name;Capacity\nA;1\nB;2\n".encode()
SECOND = "﻿Name;Capacity\nA;1\nB;3\n".encode()
MAY = "2026-05-01T06:00:00+00:00"
JUNE = "2026-06-01T06:00:00+00:00"
KEY = "secret-test-key"
PUBLISHER_TITLE = "SP ENW - Embedded Capacity Register 2 - 1MW & Above"


class Response:
    status = 200
    headers = {"Content-Type": "text/csv"}

    def __init__(self, content):
        self.content = content

    def read(self, limit):
        return self.content[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class SeriesCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.hashes = capture.load_declarations()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.editions_file = self.root / "editions/grid/uk/dno/enwl/ecr.ttl"
        environment = patch.dict("os.environ", {"ENWL_API_KEY": KEY})
        environment.start()
        self.addCleanup(environment.stop)

    def direct_capture(self):
        return capture.capture(self.graph, self.hashes, SERIES, self.root / "captures",
                               self.root / "editions", self.root / ".env")

    def run_capture(self, content, modified, rows=2, modified_after=None, graph=None, title=PUBLISHER_TITLE):
        states = [modified, modified_after or modified]
        self.downloads = 0

        def answer(url, key):
            self.assertEqual(key, KEY)
            if "/exports/csv" in url:
                self.downloads += 1
                return Response(content)
            self.assertTrue(url.endswith("/datasets/enwl-embedded-capacity-register-2-1mw-and-above"))
            return Response(json.dumps({"metas": {"default": {
                "modified": states.pop(0), "records_count": rows,
                "title": title, "description": "<p>Portal boilerplate</p>"}}}).encode())

        with patch.object(capture, "fetch", side_effect=answer), patch.object(capture, "git_revision", return_value="test"):
            if graph is None:
                return self.direct_capture()
            return capture.capture(graph, self.hashes, SERIES, self.root / "captures",
                                   self.root / "editions", self.root / ".env")

    def editions(self):
        return capture.load_editions(self.editions_file)

    def declarations_with(self, predicate, value):
        graph = Graph()
        for triple in self.graph:
            graph.add(triple)
        graph.remove((SERIES, predicate, None))
        if value is not None:
            graph.add((SERIES, predicate, value))
        return graph

    def test_every_series_tracking_a_source_dataset_is_captured(self):
        self.assertEqual(capture.capturable_series(self.graph), [SERIES])

    def test_parameters_are_derived_from_the_tracked_page_and_its_portal(self):
        parameters = capture.series_parameters(self.graph, SERIES)
        api = ("https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
               "enwl-embedded-capacity-register-2-1mw-and-above")
        self.assertEqual(parameters["metadata"], api)
        self.assertEqual(parameters["download"], api + "/exports/csv?use_labels=true")
        self.assertEqual(parameters["variable"], "ENWL_API_KEY")
        self.assertEqual(parameters["publisher"], URIRef("https://busbar.example/id/grid/uk/dno/enwl"))

    def test_key_is_not_sent_outside_the_declared_portal(self):
        graph = self.declarations_with(capture.PUB.tracksSourceDataset,
                                       URIRef("https://other.example/explore/dataset/x/"))
        with self.assertRaisesRegex(ValueError, "declared portal"):
            capture.series_parameters(graph, SERIES)

    def test_only_opendatasoft_dataset_pages_are_understood(self):
        graph = self.declarations_with(capture.PUB.tracksSourceDataset,
                                       URIRef("https://electricitynorthwest.opendatasoft.com/pages/map/"))
        with self.assertRaisesRegex(ValueError, "Not an OpenDataSoft dataset page"):
            capture.series_parameters(graph, SERIES)

    def test_publisher_and_latest_file_are_recorded_with_the_editions(self):
        self.run_capture(FIRST, MAY)
        graph = self.editions()
        self.assertIsNone(graph.value(SERIES, capture.DCTERMS.description))
        self.assertEqual(graph.value(SERIES, capture.DCTERMS.publisher),
                         URIRef("https://busbar.example/id/grid/uk/dno/enwl"))
        latest = graph.value(SERIES, capture.DCAT.distribution)
        self.assertTrue(str(graph.value(latest, capture.DCAT.downloadURL)).endswith("/exports/csv?use_labels=true"))

    def test_publisher_title_is_used_without_a_declared_title(self):
        self.run_capture(FIRST, MAY)
        graph = self.editions()
        self.assertEqual(str(graph.value(SERIES, capture.DCTERMS.title)), PUBLISHER_TITLE)
        edition = graph.value(SERIES, capture.DCAT.last)
        self.assertTrue(str(graph.value(edition, capture.DCTERMS.title)).startswith(PUBLISHER_TITLE))

    def test_declared_title_overrides_the_publisher_title(self):
        self.run_capture(FIRST, MAY, graph=self.declarations_with(capture.DCTERMS.title, Literal("Ours")))
        graph = self.editions()
        self.assertIsNone(graph.value(SERIES, capture.DCTERMS.title))
        edition = graph.value(SERIES, capture.DCAT.last)
        self.assertTrue(str(graph.value(edition, capture.DCTERMS.title)).startswith("Ours"))

    def test_new_publisher_title_is_recorded_without_a_download(self):
        self.run_capture(FIRST, MAY)
        self.run_capture(FIRST, MAY, title="Renamed")
        self.assertEqual(self.downloads, 0)
        self.assertEqual(str(self.editions().value(SERIES, capture.DCTERMS.title)), "Renamed")

    def test_first_capture_records_an_edition(self):
        record, path = self.run_capture(FIRST, MAY)
        self.assertEqual(record["status"], "success")
        self.assertTrue(record["new_edition"])
        self.assertEqual(record["row_count"], 2)
        edition = URIRef(EDITIONS + "/2026-05-01")
        self.assertEqual(record["edition"], str(edition))
        graph = self.editions()
        self.assertIn((SERIES, capture.DCAT.first, edition), graph)
        self.assertIn((SERIES, capture.DCAT.last, edition), graph)
        self.assertEqual(capture.last_edition(graph, SERIES)[1], record["content_hash"].removeprefix("sha256:"))
        self.assertTrue((self.root / "captures" / record["artifact_path"]).is_file())
        self.assertNotIn(KEY, path.read_text())

    def test_header_only_file_fails_without_an_edition(self):
        record, _ = self.run_capture(HEADER_ONLY, MAY, rows=568)
        self.assertEqual(record["status"], "failed")
        self.assertIn("Expected 568 rows", record["error"])
        self.assertFalse(self.editions_file.exists())

    def test_missing_key_fails_before_any_request(self):
        with patch.dict("os.environ", {"ENWL_API_KEY": ""}), patch.object(capture, "fetch") as fetch:
            record, _ = self.direct_capture()
        fetch.assert_not_called()
        self.assertEqual(record["status"], "failed")
        self.assertIn("ENWL_API_KEY is not set", record["error"])

    def test_key_is_read_from_env_file(self):
        env_file = self.root / ".env"
        env_file.write_text('OTHER=1\nENWL_API_KEY="from-file"\n')
        with patch.dict("os.environ", {"ENWL_API_KEY": ""}):
            self.assertEqual(capture.read_api_key("ENWL_API_KEY", env_file), "from-file")

    def test_unchanged_date_skips_the_download(self):
        self.run_capture(FIRST, MAY)
        before = self.editions_file.read_bytes()
        record, _ = self.run_capture(FIRST, MAY)
        self.assertEqual(self.downloads, 0)
        self.assertEqual(record["status"], "success")
        self.assertFalse(record["downloaded"])
        self.assertFalse(record["new_edition"])
        self.assertEqual(self.editions_file.read_bytes(), before)

    def test_same_moment_in_another_notation_skips_the_download(self):
        self.run_capture(FIRST, MAY)
        self.run_capture(FIRST, "2026-05-01T06:00:00Z")
        self.assertEqual(self.downloads, 0)

    def test_publisher_update_with_new_file_chains_editions(self):
        self.run_capture(FIRST, MAY)
        record, _ = self.run_capture(SECOND, JUNE)
        self.assertTrue(record["new_edition"])
        may, june = (URIRef(f"{EDITIONS}/{day}") for day in ("2026-05-01", "2026-06-01"))
        graph = self.editions()
        self.assertEqual(set(graph.objects(SERIES, capture.DCAT.last)), {june})
        self.assertIn((SERIES, capture.DCAT.first, may), graph)
        self.assertIn((june, capture.DCAT.prev, may), graph)

    def test_editions_file_reads_in_chronological_order(self):
        self.run_capture(FIRST, MAY)
        self.run_capture(SECOND, JUNE)
        text = self.editions_file.read_text()
        may, june = f"<{EDITIONS}/2026-05-01>", f"<{EDITIONS}/2026-06-01>"
        positions = [text.index(f"\n{subject} ") for subject in
                     (f"<{SERIES}>", f"<{SERIES}/distributions/latest-csv>", may,
                      f"<{EDITIONS}/2026-05-01/csv>", june, f"<{EDITIONS}/2026-06-01/csv>")]
        self.assertEqual(positions, sorted(positions))
        # Writing in our own order loses nothing.
        graph = self.editions()
        capture.write_editions(graph, self.root / "copy.ttl")
        self.assertTrue(isomorphic(graph, capture.load_editions(self.root / "copy.ttl")))

    def test_new_date_with_same_file_is_not_an_edition(self):
        self.run_capture(FIRST, MAY)
        record, _ = self.run_capture(FIRST, JUNE)
        self.assertEqual(self.downloads, 1)
        self.assertEqual(record["status"], "success")
        self.assertFalse(record["new_edition"])

    def test_second_update_on_the_same_day_keeps_both_editions(self):
        self.run_capture(FIRST, MAY)
        record, _ = self.run_capture(SECOND, "2026-05-01T18:30:00+00:00")
        self.assertEqual(record["edition"], f"{EDITIONS}/2026-05-01T183000Z")

    def test_update_during_download_fails(self):
        record, _ = self.run_capture(FIRST, MAY, modified_after=JUNE)
        self.assertEqual(record["status"], "failed")
        self.assertIn("during the download", record["error"])
        self.assertFalse(self.editions_file.exists())

    def test_uneven_rows_fail(self):
        record, _ = self.run_capture(b"Name;Capacity\nA\nB;2\n", MAY)
        self.assertEqual(record["status"], "failed")
        self.assertIn("different lengths", record["error"])

    def test_key_never_reaches_a_recorded_error(self):
        with patch.object(capture, "fetch", side_effect=ValueError(f"Invalid header {KEY}")):
            record, path = self.direct_capture()
        self.assertEqual(record["status"], "failed")
        self.assertNotIn(KEY, path.read_text())

    def test_http_refusal_is_recorded(self):
        refusal = HTTPError("https://example.org", 403, "Forbidden", {}, None)
        self.addCleanup(refusal.close)
        with patch.object(capture, "fetch", side_effect=refusal):
            record, _ = self.direct_capture()
        self.assertEqual(record["http_status"], 403)

    def test_redirects_are_refused(self):
        self.assertIsNone(capture.RefuseRedirects().redirect_request(None, None, 302, "Found", {}, "https://other.example/"))


if __name__ == "__main__":
    unittest.main()
