"""Run against both editable installs and wheels (including outside the checkout)."""
import contextlib
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import busbar
from busbar import capture_catalogue, cli, resources
from rdflib import RDF, Namespace


class PackageTests(unittest.TestCase):
    def test_public_graph_loaders_are_independent(self):
        catalogue = busbar.load_catalogue()
        ontology = busbar.load_ontology()
        self.assertGreater(len(catalogue), 0)
        self.assertGreater(len(ontology), 0)
        count = len(catalogue)
        catalogue.remove((None, None, None))
        self.assertEqual(len(busbar.load_catalogue()), count)
        dcat = Namespace("http://www.w3.org/ns/dcat#")
        self.assertEqual(len(set(busbar.load_catalogue().subjects(RDF.type, dcat.Dataset))), 220)

    def test_all_resources_and_declaration_hashes_are_available(self):
        root = resources.data_root()
        graph, hashes = busbar.load_declarations()
        self.assertGreater(len(graph), 0)
        self.assertTrue(hashes)
        for name, digest in hashes.items():
            self.assertEqual(hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest(), digest)
        self.assertTrue(root.joinpath("shapes/publishing.ttl").is_file())
        self.assertTrue(root.joinpath("queries/list-observations.rq").is_file())

    def test_custom_declaration_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = resources.data_root()
            for name in ("definitions", "vocabulary", "shapes"):
                self.copy_resources(source.joinpath(name), root / name)
            self.assertEqual(busbar.load_declarations()[1], busbar.load_declarations(root)[1])
            with self.assertRaises(FileNotFoundError):
                busbar.load_declarations(root / "missing")

    @staticmethod
    def copy_resources(source, destination):
        destination.mkdir(parents=True)
        for child in source.iterdir():
            if child.is_dir():
                PackageTests.copy_resources(child, destination / child.name)
            else:
                (destination / child.name).write_bytes(child.read_bytes())

    def test_resources_support_nonfilesystem_traversables(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "data.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                source = resources.data_root()
                for name in ("definitions", "vocabulary", "shapes"):
                    for relative, resource in resources.turtle_files(source.joinpath(name)):
                        zipped.writestr(f"data/{name}/{relative}", resource.read_bytes())
                zipped.writestr("data/catalogue.ttl", source.joinpath("catalogue.ttl").read_bytes())
            expected_count = len(busbar.load_catalogue())
            with zipfile.ZipFile(archive) as zipped:
                root = zipfile.Path(zipped, "data/")
                with patch.object(resources, "files", return_value=zipfile.Path(zipped)):
                    self.assertEqual(len(resources.load_catalogue()), expected_count)
                    self.assertTrue(busbar.load_declarations()[1])
                self.assertTrue(root.is_dir())

    def test_no_git_is_required(self):
        with patch.object(capture_catalogue.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(capture_catalogue.git_revision())
        with patch.object(capture_catalogue, "source_root", return_value=None):
            self.assertIsNone(capture_catalogue.git_revision())

    def test_cli_validation_is_offline_and_creates_no_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-m", "busbar", "capture", "--validate-only"],
                cwd=directory, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Validated", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_all_cli_help(self):
        for command in cli.COMMANDS:
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    cli.main([command, "--help"])
                self.assertEqual(result.exception.code, 0)

    def test_default_capture_output_is_in_working_directory(self):
        # Validate the parsed default without making any HTTP requests.
        with patch.object(capture_catalogue, "capture") as capture:
            capture.return_value = ({"status": "success"}, Path("observation.json"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["capture"]), 0)
            self.assertEqual(capture.call_args.args[3], Path.cwd() / "captures")


if __name__ == "__main__":
    unittest.main()
