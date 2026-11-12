# Using and developing Busbar

Busbar is a work-in-progress research project. This guide covers the current
Python package, local tools and optional automation. For the research scope and
roadmap, see the [project overview](../README.md).

## Install and use from Python

Busbar requires Python 3.11 or newer. Install directly from GitHub with
[uv](https://docs.astral.sh/uv/) (pin a tag or commit for reproducible deployments):

```bash
uv add "busbar @ git+https://github.com/piotch/busbar.git"
# Optional S3-compatible storage support:
uv add "busbar[s3] @ git+https://github.com/piotch/busbar.git"
```

These commands require a revision containing the Python package. Until this branch
is merged, append `@feat/python-package` to the Git URL. Standard pip also works:

```bash
pip install "busbar @ git+https://github.com/piotch/busbar.git"
```

```python
import busbar

catalogue = busbar.load_catalogue()  # Fresh rdflib.Graph; no network access.
ontology = busbar.load_ontology()
declarations, hashes = busbar.load_declarations()  # Includes SHACL validation.
```

The wheel includes the curated catalogue, ontology, source definitions,
vocabularies, SHACL shapes and example SPARQL queries. Installing Busbar does not
capture remote catalogues or download datasets. S3 credentials are only needed
for explicit bucket operations; the core library has no boto3 dependency.

### Command line

```bash
uv run busbar capture --validate-only
uv run busbar capture
uv run busbar capture-all
uv run busbar capture-series  # Needs ENWL_API_KEY; files stay local, in captures/series/.
uv run busbar build-observations
uv run busbar build-ontology
uv run --extra s3 busbar bucket check  # From this repository.
```

Each command has `--help`. In a consuming project, install the `[s3]` extra with
`uv add` as above, then use `uv run busbar bucket check` without `--extra`.
`python -m busbar` is also supported.

Captures and exports default to `captures/` and `build/` **in the current working
directory**, never inside the installed package. Use `--output`, `--captures`,
`--summary` or `--build` to select other locations. Bucket commands load `.env`
from the current directory (or `--env-file`); existing environment variables win.

### Development and releases

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv build  # Builds an sdist, then a wheel from it in dist/.
```

`uv sync` installs an editable package. Keep editing the canonical RDF files at
this repository's root and under `definitions/`, `vocabulary/` and `shapes/`;
release builds bundle those same files without maintaining a second copy.
Commit `uv.lock` for reproducible repository development; consuming projects
resolve their own dependency versions. PyPI publishing is not configured yet.

## Interactive ontology atlas

Explore the local ontologies and catalogue as a layered Three.js line drawing:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
# Open http://localhost:8000/visualisation/
```

Orbit, pan and zoom; focus layers, search entities and inspect asserted links and
source files. Internet access is needed for the pinned Three.js CDN dependency.
See [the atlas guide](../visualisation/README.md) for controls, projection scope and
how to refresh the RDF export. The [GitHub Pages publishing guide](github-pages.md)
explains automatic deployment, the public artifact boundary and the one-time
repository settings needed to publish the atlas.

## Viewing in Protégé

Generate an independent RDF/XML ontology containing the news/source vocabulary,
source definitions and the latest successfully captured DCAT catalogues for all six DNOs. Shared identities, including Busbar and ReferenceWorks, are included.
The original grid-domain vocabulary and Busbar's curated series membership are
not merged into this flat viewer file:

```bash
uv run busbar build-ontology
open -a "$HOME/Applications/Protégé.app" build/news-catalogues.owl
```

The generated `build/` directory is ignored by Git. Edit the source Turtle files,
not the viewer export. One capture per publisher is included, with separate
catalogue membership and capture provenance; SHACL shapes are used for validation but are not merged into this file.
Capture all sources first if their observations are not present. The builder
fails rather than silently skipping a missing source. Select particular captures
with repeated `--observation captures/observations/<observation>.json` arguments,
or select sources with repeated `--spec <specification-IRI>` arguments. In Protégé, use **Entities** to browse classes and individuals;
enable **Window → Tabs → OntoGraf** for an interactive relationship diagram.

## Queryable observation history (TriG)

```bash
uv run busbar build-observations
```

This writes ignored `build/observations.trig`: one named graph per successful
capture, an observation metadata graph, a current-definitions graph, and a separate
Busbar curated-catalogue graph. These can be queried together without merging
publisher assertions with curator assertions.
Repeated observations remain separate even when their content is identical.
Failed acquisitions have metadata but no snapshot graph. Original publisher
identifiers are preserved inside each snapshot; canonical source identities are
linked through the metadata, not merged across historical states.

See [source tracking](source-tracking.md#trig-observation-history) for
SPARQL examples. Protégé's flat OWL export remains a separate viewer artifact.

## Scheduled capture with GitHub Actions

For optional UK-based SSEN acquisition without changing source definitions, see
[the London Lambda relay setup](ssen-relay.md).

The [Catalogue observations workflow](../.github/workflows/catalogue-observations.yml)
can capture public catalogues daily and on manual dispatch, persisting history in
the S3-compatible bucket and publishing versioned exports. Pull requests only run
validation and tests; they never access bucket credentials.

Configure the repository secrets first—the local `.env` is not available on a
GitHub runner. See [GitHub Actions setup and storage](github-actions.md).
