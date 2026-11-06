import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from busbar import capture_series as capture
from rdflib import Graph, URIRef

SERIES = URIRef("https://busbar.example/id/grid/uk/dno/enwl/series/ecr")
EDITIONS = "https://busbar.example/id/grid/uk/dno/enwl/editions/ecr"
HEADER_ONLY = "﻿Name;Capacity\n".encode()
FIRST = "﻿Name;Capacity\nA;1\nB;2\n".encode()
SECOND = "﻿Name;Capacity\nA;1\nB;3\n".encode()
MAY = "2026-05-01T06:00:00+00:00"
JUNE = "2026-06-01T06:00:00+00:00"
KEY = "secret-test-key"


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

    def run_capture(self, content, modified, rows=2, modified_after=None):
        states = [modified, modified_after or modified]
        self.downloads = 0

        def answer(url, key):
            self.assertEqual(key, KEY)
            if "/exports/csv" in url:
                self.downloads += 1
                return Response(content)
            self.assertTrue(url.endswith("/datasets/enwl-embedded-capacity-register-2-1mw-and-above"))
            return Response(json.dumps({"metas": {"default": {"modified": states.pop(0), "records_count": rows}}}).encode())

        with patch.object(capture, "fetch", side_effect=answer), patch.object(capture, "git_revision", return_value="test"):
            return self.direct_capture()

    def editions(self):
        return capture.load_editions(self.editions_file)

    def test_every_series_with_a_distribution_is_captured(self):
        self.assertEqual(capture.capturable_series(self.graph), [SERIES])

    def test_parameters_come_from_the_series_and_its_portal(self):
        _, download, metadata, variable = capture.series_parameters(self.graph, SERIES)
        self.assertEqual(download, metadata + "/exports/csv?use_labels=true")
        self.assertEqual(variable, "ENWL_API_KEY")

    def test_key_is_not_sent_outside_the_declared_portal(self):
        graph = Graph()
        for subject, predicate, value in self.graph:
            if predicate == capture.DCAT.downloadURL:
                value = URIRef("https://other.example/api/datasets/x/exports/csv")
            graph.add((subject, predicate, value))
        with self.assertRaisesRegex(ValueError, "declared portal"):
            capture.series_parameters(graph, SERIES)

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
