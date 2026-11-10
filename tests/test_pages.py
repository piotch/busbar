"""Verify the public Pages artifact, without network access or deployment."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'visualisation/build_pages.py'
REVISION = 'a' * 40
REPOSITORY = 'example/atlas'
PUBLIC_FILES = {
    'index.html', 'style.css', 'app.js', 'atlas-layout.js', 'grid-layout.js',
    'grid-layout-config.js', 'view-utils.js', 'graph.json', 'site.json',
    'LICENSE', '.nojekyll',
}


def stage(output, *, repository=REPOSITORY, revision=REVISION):
    return subprocess.run(
        [sys.executable, str(BUILDER), '--output', str(output),
         '--repository', repository, '--revision', revision],
        cwd=output.parent, capture_output=True, text=True,
    )


class PagesArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.output = Path(cls.temporary.name) / 'site'
        result = stage(cls.output)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def test_artifact_is_an_explicit_allowlist_not_a_repository_copy(self):
        self.assertEqual({path.name for path in self.output.iterdir()}, PUBLIC_FILES)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in self.output.iterdir()))
        # No capture bytes, credentials, source tools, tests or old build exports.
        self.assertFalse(any(path.suffix in {'.csv', '.py', '.ttl', '.trig', '.owl', '.zip'} for path in self.output.rglob('*')))
        self.assertEqual((self.output / 'LICENSE').read_bytes(), (ROOT / 'LICENSE').read_bytes())

    def test_deployed_source_links_are_pinned_to_a_commit_and_support_forks(self):
        site = json.loads((self.output / 'site.json').read_text())
        self.assertEqual(site['repositoryUrl'], 'https://github.com/example/atlas')
        self.assertEqual(site['sourceBaseUrl'], f'https://github.com/example/atlas/blob/{REVISION}/')
        self.assertEqual(site['revision'], REVISION)

    def test_staged_graph_matches_the_current_public_projection(self):
        self.assertEqual(
            json.loads((self.output / 'graph.json').read_text()),
            json.loads((ROOT / 'visualisation/graph.json').read_text()),
        )

    def test_local_module_and_fetch_dependencies_are_staged(self):
        for path in self.output.glob('*.js'):
            text = path.read_text()
            for relative in re.findall(r"(?:from\s+|fetch\()'\./([^']+)'", text):
                self.assertIn(relative, PUBLIC_FILES, f'{path.name}: {relative}')
                self.assertTrue((self.output / relative).is_file())
        html = (self.output / 'index.html').read_text()
        self.assertIn('href="style.css"', html)
        self.assertIn("import('./app.js')", html)

    def test_existing_output_is_never_overwritten_or_published_with_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'occupied'
            output.mkdir()
            marker = output / '.env'
            marker.write_text('test-canary-not-a-real-secret')
            result = stage(output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Refusing non-empty output', result.stderr)
            self.assertEqual(marker.read_text(), 'test-canary-not-a-real-secret')
            self.assertEqual([path.name for path in output.iterdir()], ['.env'])

    def test_output_symlinks_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.mkdir()
            alias = Path(directory) / 'alias'
            try:
                alias.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('Symlinks are unavailable')
            result = stage(alias)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Refusing a symlink', result.stderr)
            self.assertEqual(list(target.iterdir()), [])

    def test_invalid_repository_or_mutable_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            for repository, revision in [('example/atlas', 'main'), ('example/atlas', 'abc123'),
                                         ('https://github.com/example/atlas', REVISION),
                                         ('example/atlas/extra', REVISION),
                                         ('../atlas', REVISION)]:
                with self.subTest(repository=repository, revision=revision):
                    result = stage(output, repository=repository, revision=revision)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
