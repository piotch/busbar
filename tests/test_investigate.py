import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from rdflib import Graph, Literal, RDF, URIRef

from busbar import investigate as agent
from busbar.report_changes import CHANGE, DCT, PROV

DATASET = "https://publisher.example/dataset/substations"
CATALOG = "https://busbar.example/id/grid/uk/dno/nged/catalogue"
REPO = "owner/busbar"


def report_bytes():
    graph = Graph()
    event, activity = URIRef("urn:event"), URIRef("urn:comparison")
    graph.add((event, CHANGE.dataset, URIRef(DATASET)))
    graph.add((event, CHANGE.catalog, URIRef(CATALOG)))
    graph.add((event, RDF.type, CHANGE.MetadataUpdated))
    graph.add((event, CHANGE.previousDayRecurrence, CHANGE.Unknown))
    graph.add((event, CHANGE.windowStart, Literal("2026-11-01T12:00:00+00:00")))
    graph.add((event, CHANGE.windowEnd, Literal("2026-11-02T12:00:00+00:00")))
    graph.add((event, PROV.wasGeneratedBy, activity))
    graph.add((activity, CHANGE.previousSnapshot, URIRef("urn:before")))
    graph.add((activity, CHANGE.latestSnapshot, URIRef("urn:after")))
    graph.add((URIRef(DATASET), DCT.title, Literal("Distribution Substations")))
    return graph.serialize(format="xml").encode()


def model_draft():
    return {"summary": "Inspect substation identifiers.", "drafts": [
        {"dataset": DATASET, "title": "Investigate distribution substations",
         "body": "## Observed facts\nMetadata changed.\n## Uncertainty\nNo file inspected."}]}


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.report = self.root / "changes.rdf"
        self.report.write_bytes(report_bytes())
        self.run = self.root / "run"

    def plan(self, command="triage", existing=None, **options):
        args = argparse.Namespace(repo=REPO, report=self.report, command=command,
                                  dataset=DATASET, evidence=[], max_candidates=3,
                                  run=self.run, prepare_only=False, model="test/model", timeout=30)
        for key, value in options.items():
            setattr(args, key, value)
        with patch.object(agent, "issues", return_value=existing or []), \
                patch.object(agent, "ask_pi", return_value=model_draft()) as ask, \
                patch("sys.stdout", new_callable=io.StringIO):
            agent.plan(args)
        return ask

    def proposal(self):
        return json.loads((self.run / "proposal.json").read_text())

    def approval(self):
        return argparse.Namespace(run=self.run, repo=REPO,
                                  approve=hashlib.sha256((self.run / "proposal.json").read_bytes()).hexdigest())

    def test_plan_only_and_pinned_evidence(self):
        self.plan()
        proposal = self.proposal()
        self.assertEqual(proposal["actions"][0]["kind"], "issue")
        self.assertEqual(proposal["report_sha256"], hashlib.sha256(report_bytes()).hexdigest())
        self.assertIn("urn:before", proposal["actions"][0]["body"])
        self.assertTrue((self.run / "packet.json").exists())
        self.assertTrue((self.run / "proposal.md").exists())
        with self.assertRaises(FileExistsError):
            self.plan()

    def test_prepare_only_never_invokes_model(self):
        ask = self.plan(prepare_only=True)
        ask.assert_not_called()
        self.assertFalse((self.run / "proposal.json").exists())

    def test_existing_issue_becomes_comment(self):
        marker = agent.issue_marker(REPO, CATALOG, DATASET)
        self.plan(existing=[{"number": 7, "state": "open", "body": marker}])
        action = self.proposal()["actions"][0]
        self.assertEqual((action["kind"], action["issue"]), ("comment", 7))

    def test_closed_or_ambiguous_issue_blocks_proposal(self):
        with self.assertRaisesRegex(ValueError, "Closed or ambiguous"):
            self.plan(existing=[{"number": 7, "state": "closed", "body": DATASET}])
        self.assertFalse((self.run / "proposal.json").exists())

    def test_inspect_requires_evidence_and_reads_comments(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.plan(command="inspect")
        evidence = self.root / "shape.json"
        evidence.write_text('{"fields": ["id", "primary"]}')
        with patch.object(agent, "gh_api", return_value=[[{"body": "Earlier findings"}]]):
            ask = self.plan(command="inspect", evidence=[evidence],
                            existing=[{"number": 7, "state": "open", "body": DATASET}])
        packet = ask.call_args.args[0]
        self.assertEqual(packet["existing_issues"][0]["comments"], ["Earlier findings"])
        self.assertEqual(packet["evidence"][0]["sha256"], hashlib.sha256(evidence.read_bytes()).hexdigest())

    def test_malformed_or_unknown_model_output_fails_closed(self):
        for value in [{}, {"summary": "x", "drafts": [{"dataset": "unknown", "title": "x", "body": "y"}]},
                      {"summary": "x", "drafts": [model_draft()["drafts"][0]] * 2}]:
            with self.assertRaises(ValueError):
                agent.validate_drafts(value, {DATASET}, 3)

    def test_pi_has_no_tools_and_no_write_credentials(self):
        completed = Mock(returncode=0, stdout=json.dumps(model_draft()))
        with patch.dict("os.environ", {"GH_TOKEN": "secret", "BUCKET_SECRET_KEY": "secret",
                                       "AWS_SECRET_ACCESS_KEY": "secret"}), \
                patch.object(agent.subprocess, "run", return_value=completed) as run:
            agent.ask_pi({"evidence": "untrusted"}, "provider/model", 40)
        argv = run.call_args.args[0]
        for flag in ("--no-tools", "--no-mcp", "--no-extensions", "--no-context-files", "--no-session"):
            self.assertIn(flag, argv)
        self.assertNotIn("GH_TOKEN", run.call_args.kwargs["env"])
        self.assertNotIn("BUCKET_SECRET_KEY", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["timeout"], 40)

    def test_hash_approval_required_and_no_further_writes_after_edit(self):
        self.plan()
        args = self.approval()
        (self.run / "proposal.json").write_text((self.run / "proposal.json").read_text() + " ")
        with patch.object(agent, "gh_api") as gh:
            with self.assertRaisesRegex(ValueError, "Approval hash"):
                agent.apply(args)
            gh.assert_not_called()

    def test_apply_create_and_idempotent_retry(self):
        self.plan()
        with patch.object(agent, "issues", return_value=[]), \
                patch.object(agent, "gh_api", return_value={"html_url": "https://github.com/owner/busbar/issues/7"}) as gh, \
                patch("sys.stdout", new_callable=io.StringIO):
            agent.apply(self.approval())
        self.assertEqual(gh.call_args.args[2], "POST")
        item = {"number": 7, "state": "open", "body": self.proposal()["actions"][0]["body"],
                "html_url": "https://github.com/owner/busbar/issues/7"}
        with patch.object(agent, "issues", return_value=[item]), \
                patch.object(agent, "gh_api", return_value=[[]]) as gh, \
                patch("sys.stdout", new_callable=io.StringIO):
            agent.apply(self.approval())
        self.assertEqual(len(gh.call_args.args), 2)  # Read comments only, no POST.
        self.assertTrue(json.loads((self.run / "receipts.json").read_text())[0]["skipped"])
        self.assertFalse((self.run / "apply.lock").exists())

    def test_changed_targets_and_races_stop(self):
        self.plan()
        item = {"number": 9, "state": "open", "body": DATASET}
        with patch.object(agent, "issues", return_value=[item]), \
                patch.object(agent, "gh_api", return_value=[[]]) as gh:
            with self.assertRaisesRegex(ValueError, "re-plan"):
                agent.apply(self.approval())
            self.assertEqual(len(gh.call_args.args), 2)
        self.assertFalse((self.run / "apply.lock").exists())

    def test_unsupported_action_and_wrong_repo_rejected(self):
        self.plan()
        proposal = self.proposal()
        proposal["actions"][0]["kind"] = "merge"
        (self.run / "proposal.json").write_text(agent.encoded(proposal))
        with patch.object(agent, "gh_api") as gh:
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                agent.apply(self.approval())
            gh.assert_not_called()
        args = self.approval()
        args.repo = "different/repo"
        with self.assertRaisesRegex(ValueError, "Wrong repository"):
            agent.apply(args)

    def test_file_shape_comparison_no_row_values(self):
        before, after = self.root / "before.csv", self.root / "after.csv"
        before.write_text("id,name\n1,Private customer\n")
        after.write_text("id,name,primary\n1,Private customer,P1\n")
        output = self.root / "shape.json"
        agent.inspect_data(argparse.Namespace(input=after, previous=before, output=output))
        result = json.loads(output.read_text())
        self.assertEqual(result["added_fields"], ["primary"])
        self.assertNotIn("Private customer", output.read_text())
        self.assertEqual(result["current"]["record_or_triple_count"], 1)

    def test_file_limits_formats_and_ragged_csv(self):
        path = self.root / "data.csv"
        path.write_text("a,b\n1\n")
        with self.assertRaisesRegex(ValueError, "Ragged"):
            agent.data_shape(path)
        with self.assertRaises(ValueError):
            agent.bounded(path, limit=2)
        path = self.root / "data.json"
        path.write_text('[{"id": 1}, {"id": "two", "name": null}]')
        result = agent.data_shape(path)
        self.assertEqual(result["fields"]["id"], ["int", "str"])
        path.write_text('{"not": "an array"}')
        with self.assertRaises(ValueError):
            agent.data_shape(path)

    def test_finding_marker_stable_across_regenerated_report(self):
        first = agent.report_candidates(report_bytes())[0]
        second = json.loads(json.dumps(first))
        second["events"][0]["event"] = "urn:different-report-event"
        second["events"][0]["statements"] = [["added", "_:regenerated", "p", "o"]]
        self.assertEqual(agent.finding_marker(first, "triage", []),
                         agent.finding_marker(second, "triage", []))

    def test_apply_comment_and_retry(self):
        self.plan(existing=[{"number": 7, "state": "open", "body": DATASET}])
        item = {"number": 7, "state": "open", "body": DATASET,
                "html_url": "https://github.com/owner/busbar/issues/7"}
        with patch.object(agent, "issues", return_value=[item]), \
                patch.object(agent, "gh_api", side_effect=[[[]], {"html_url": "comment-url"}]) as gh, \
                patch("sys.stdout", new_callable=io.StringIO):
            agent.apply(self.approval())
        self.assertEqual(gh.call_args.args[1:3], ("issues/7/comments", "POST"))
        comment = {"body": self.proposal()["actions"][0]["body"]}
        with patch.object(agent, "issues", return_value=[item]), \
                patch.object(agent, "gh_api", return_value=[[comment]]) as gh, \
                patch("sys.stdout", new_callable=io.StringIO):
            agent.apply(self.approval())
        self.assertEqual(gh.call_count, 1)

    def test_failure_and_closed_apply_leave_no_lock(self):
        self.plan()
        with patch.object(agent, "issues", return_value=[]), \
                patch.object(agent, "gh_api", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                agent.apply(self.approval())
        self.assertFalse((self.run / "apply.lock").exists())
        with patch.object(agent, "issues", return_value=[{"state": "closed", "body": DATASET}]), \
                patch.object(agent, "gh_api") as gh:
            with self.assertRaises(ValueError):
                agent.apply(self.approval())
            gh.assert_not_called()

    def test_invalid_rdf_and_missing_provenance(self):
        with self.assertRaises(Exception):
            agent.report_candidates(b"not RDF")
        graph = Graph().parse(data=report_bytes(), format="xml")
        graph.remove((None, CHANGE.previousSnapshot, None))
        with self.assertRaisesRegex(ValueError, "snapshot provenance"):
            agent.report_candidates(graph.serialize(format="xml").encode())

    def test_github_pagination_and_pr_exclusion(self):
        with patch.object(agent, "gh_api", return_value=[[{"number": 1}],
                                                         [{"number": 2, "pull_request": {}}, {"number": 3}]]):
            self.assertEqual([x["number"] for x in agent.issues(REPO)], [1, 3])

    def test_github_api_uses_arguments_and_json_stdin(self):
        with patch.object(agent, "run_command", return_value='{"html_url":"url"}') as run:
            agent.gh_api(REPO, "issues", "POST", {"title": "$(untrusted)", "body": "x"})
        self.assertNotIn("$(untrusted)", run.call_args.args[0])
        self.assertEqual(json.loads(run.call_args.kwargs["input"])["title"], "$(untrusted)")
        with self.assertRaises(ValueError):
            agent.repository("owner/repo/extra")


if __name__ == "__main__":
    unittest.main()
