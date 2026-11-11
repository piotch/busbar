import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

from rdflib import BNode, Dataset, Graph, Literal, RDF, URIRef
from rdflib.compare import isomorphic

from busbar.build_observations import DCAT, DCT, METADATA, PROV, PUB
from busbar.report_changes import CHANGE, load_bucket_archive, main, markdown, report
from busbar.bucket_store import Settings


class ReportTests(unittest.TestCase):
    def archive(self, states, hours=24, start=None):
        archive = Dataset(default_union=False)
        metadata = archive.graph(METADATA)
        start = start or datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        for i, state in enumerate(states):
            node = URIRef(f"urn:observation:{i}")
            metadata.add((node, RDF.type, PUB.CatalogSnapshot))
            metadata.add((node, PUB.status, Literal("success" if state is not None else "failed")))
            metadata.add((node, PUB.observedCatalog, URIRef("https://example.org/nged/catalogue")))
            metadata.add((node, PROV.generatedAtTime, Literal((start + timedelta(hours=i * hours)).isoformat())))
            for name, title in (state or {}).items():
                graph = archive.graph(node)
                dataset = URIRef(f"urn:dataset:{name}")
                graph.add((dataset, RDF.type, DCAT.Dataset))
                graph.add((dataset, DCT.title, Literal(title)))
                blank = BNode()
                graph.add((dataset, DCT.publisher, blank))
                graph.add((blank, DCT.title, Literal("Publisher")))
        return archive

    def events(self, graph):
        return list(graph.subjects(CHANGE.dataset, None))

    def test_membership_failures_and_baseline(self):
        result = report(self.archive([{"a": "A"}, None, {"b": "B"}]))
        self.assertEqual(len(list(result.subjects(RDF.type, CHANGE.ListingAdded))), 1)
        self.assertEqual(len(list(result.subjects(RDF.type, CHANGE.ListingRemoved))), 1)
        self.assertNotIn((None, PROV.used, URIRef("urn:observation:1")), result)
        baseline = report(self.archive([{"a": "A"}]))
        self.assertEqual(self.events(baseline), [])
        self.assertIn((None, CHANGE.comparisonStatus, CHANGE.BaselineOnly), baseline)

    def test_unchanged_and_repeated_updates_suppressed(self):
        for states in [[{"a": "A"}] * 4, [{"a": "A"}, {"a": "B"}, {"a": "C"}],
                       [{"a": "A"}, {"a": "B"}, {"a": "B"}]]:
            self.assertEqual(self.events(report(self.archive(states))), [])

    def test_retained_update_evidence_and_roundtrip(self):
        result = report(self.archive([{"a": "A"}, {"a": "A"}, {"a": "B"}]))
        event, = self.events(result)
        self.assertIn((event, CHANGE.previousDayRecurrence, CHANGE.NotObserved), result)
        self.assertIn((event, CHANGE.changedPredicate, DCT.title), result)
        added, = result.objects(event, CHANGE.addedStatement)
        removed, = result.objects(event, CHANGE.removedStatement)
        self.assertEqual(result.value(added, RDF.object), Literal("B"))
        self.assertEqual(result.value(removed, RDF.object), Literal("A"))
        self.assertTrue(isomorphic(result, Graph().parse(data=result.serialize(format="xml"), format="xml")))
        self.assertIn("NGED | urn:dataset:a | B", markdown(result))

    def test_unknown_recurrence_and_sparse_sampling(self):
        for states, hours in [([{"a": "A"}, {"a": "B"}], 24),
                              ([{"a": "A"}, {"a": "A"}, {"a": "B"}], 72)]:
            result = report(self.archive(states, hours=hours))
            event, = self.events(result)
            self.assertIn((event, CHANGE.previousDayRecurrence, CHANGE.Unknown), result)

    def test_calendar_day_not_previous_capture(self):
        # Captures at Jan 1 noon, Jan 2 midnight/noon, Jan 3 midnight/noon.
        # Dataset changed Jan 2 but not at its final capture. Still suppress it.
        states = [{"a": "A"}, {"a": "B"}, {"a": "B"}, {"a": "B"}, {"a": "C"}]
        self.assertEqual(self.events(report(self.archive(states, hours=12))), [])

    def test_reappearance_does_not_borrow_prior_history(self):
        result = report(self.archive([{"a": "A"}, {}, {"a": "B"}, {"a": "C"}]))
        event, = self.events(result)
        self.assertIn((event, CHANGE.previousDayRecurrence, CHANGE.Unknown), result)

    def test_uri_distribution_changes_and_other_catalogue_isolation(self):
        archive = self.archive([{"a": "A"}] * 3)
        for i in range(3):
            graph = archive.graph(URIRef(f"urn:observation:{i}"))
            graph.add((URIRef("urn:dataset:a"), DCAT.distribution, URIRef("urn:distribution")))
            graph.add((URIRef("urn:distribution"), DCT.modified, Literal(str(i // 2))))
            graph.add((URIRef("urn:unrelated"), DCT.title, Literal(str(i))))
        result = report(archive)
        event, = self.events(result)
        self.assertIn((event, CHANGE.changedPredicate, DCT.modified), result)
        self.assertNotIn((event, CHANGE.changedPredicate, DCT.title), result)

    def test_multiple_catalogues_and_duplicate_times(self):
        archive = self.archive([{"a": "A"}, {"a": "B"}])
        m = archive.graph(METADATA)
        node = URIRef("urn:other")
        m.add((node, RDF.type, PUB.CatalogSnapshot))
        m.add((node, PUB.status, Literal("success")))
        m.add((node, PUB.observedCatalog, URIRef("urn:other:catalogue")))
        m.add((node, PROV.generatedAtTime, Literal("2026-01-02T12:00:00+00:00")))
        result = report(archive)
        self.assertEqual(len(self.events(result)), 1)
        self.assertEqual(len(list(result.objects(None, CHANGE.comparison))), 2)
        m.set((URIRef("urn:observation:1"), PROV.generatedAtTime,
               Literal("2026-01-01T12:00:00+00:00")))
        with self.assertRaisesRegex(ValueError, "simultaneous"):
            report(archive)

    def test_cli_bucket_default_and_local_override(self):
        with patch("busbar.report_changes.load_bucket_archive", return_value=self.archive([])) as load, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main([]), 0)
            load.assert_called_once()
            Graph().parse(data=output.getvalue(), format="xml")
        with patch("busbar.report_changes.load_bucket_archive", side_effect=ValueError("secret")), \
                patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(main([]), 1)
            self.assertNotIn("secret", error.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "observations.trig"
            self.archive([{"a": "A"}, {"a": "B"}]).serialize(destination=path, format="trig")
            with patch("busbar.report_changes.load_bucket_archive") as load:
                self.assertEqual(main(["--input", str(path), "--output", str(root / "changes.rdf"),
                                       "--markdown", str(root / "changes.md")]), 0)
                load.assert_not_called()
            Graph().parse(root / "changes.rdf", format="xml")
            self.assertIn("Dataset ID", (root / "changes.md").read_text())

    def test_bucket_export_integrity_and_path(self):
        content = self.archive([{"a": "A"}]).serialize(format="trig").encode()
        settings = Settings("https://bucket.example")
        entry = {"uri": settings.uri + "/exports/run/observations.trig",
                 "sha256": hashlib.sha256(content).hexdigest()}
        # Stub optional dotenv so this test also runs in the base installed wheel.
        with patch.dict("sys.modules", {"dotenv": Mock()}), \
                patch("busbar.bucket_store.Settings.from_env", return_value=settings), \
                patch("busbar.bucket_store.client_for") as factory, \
                patch("busbar.bucket_store.read_remote") as read:
            client = factory.return_value
            body = client.get_object.return_value["Body"]
            body.read.return_value = content
            read.return_value = json.dumps({"files": {"observations.trig": entry}})
            self.assertEqual(self.events(report(load_bucket_archive(Path(".env")))), [])
            body.close.assert_called_once()
            entry["sha256"] = "0" * 64
            read.return_value = json.dumps({"files": {"observations.trig": entry}})
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_bucket_archive(Path(".env"))
            for uri in ["s3://other/exports/run/observations.trig",
                        settings.uri + "/exports/../observations.trig"]:
                entry["uri"] = uri
                read.return_value = json.dumps({"files": {"observations.trig": entry}})
                with self.assertRaises(ValueError):
                    load_bucket_archive(Path(".env"))


if __name__ == "__main__":
    unittest.main()
