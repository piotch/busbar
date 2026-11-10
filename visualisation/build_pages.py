"""Stage a public, self-contained atlas directory for GitHub Pages.

Only explicitly allowlisted browser assets, freshly generated public RDF metadata
and the license are published. Never copy the repository or runtime captures.
Run from any directory; an existing non-empty output directory is refused.
"""
import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

from export_graph import build as build_graph

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = (
    'index.html', 'style.css', 'app.js', 'atlas-layout.js', 'grid-layout.js',
    'grid-layout-config.js', 'view-utils.js',
)


def build_site(output, repository, revision):
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            or any(part in {'.', '..'} for part in repository.split('/'))):
        raise ValueError('Repository must be an owner/name pair, without a URL or extra path')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', revision):
        raise ValueError('Revision must be a full Git commit SHA, not a branch name')
    output = Path(output).expanduser()
    if output.is_symlink():
        raise ValueError('Refusing a symlink output directory')
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f'Refusing non-empty output: {output}. Choose a fresh directory.')
    for asset in ASSETS:
        if not (HERE / asset).is_file() or (HERE / asset).is_symlink():
            raise ValueError(f'Missing or symlinked browser asset: {asset}')
    # Rebuild from canonical RDF, not the checked-in JSON or captured datasets.
    # This does not modify the checkout's graph.json.
    graph = build_graph()
    revision = revision.lower()
    repository_url = f'https://github.com/{repository}'
    site = {
        'repositoryUrl': repository_url,
        'sourceBaseUrl': f'{repository_url}/blob/{revision}/',
        'revision': revision,
    }
    output.mkdir(parents=True, exist_ok=True)
    for asset in ASSETS:
        shutil.copyfile(HERE / asset, output / asset)
    (output / 'graph.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'site.json').write_text(json.dumps(site, indent=2) + '\n', encoding='utf-8')
    (output / '.nojekyll').write_text('', encoding='utf-8')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    return graph


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/pages')
    parser.add_argument('--repository', default='piotch/busbar', help='GitHub owner/name; override for a fork')
    parser.add_argument('--revision', help='Full commit SHA (defaults to this checkout HEAD)')
    args = parser.parse_args(argv)
    revision = args.revision
    if revision is None:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    try:
        graph = build_site(args.output, args.repository, revision)
    except ValueError as error:
        parser.error(str(error))
    print(f'Staged {args.output.resolve()}: {len(graph["nodes"])} nodes, {len(graph["links"])} links; commit {revision}')


if __name__ == '__main__':
    main()
