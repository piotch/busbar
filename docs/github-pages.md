# Publishing the ontology atlas on GitHub Pages

The atlas is a static website. No server, database, API credentials or publisher
capture is needed to build or deploy it.

Expected project URL: **https://piotch.github.io/busbar/** (after Pages is enabled
and the first deployment succeeds). Forks use their own Pages project URL.

## One-time repository setup

1. Push the feature branch and merge its pull request into `main`.
2. In **Settings → Pages → Build and deployment → Source**, select
   **GitHub Actions**. This requires repository administration access.
3. Check that the `github-pages` environment permits deployments from `main`
   (or approve the deployment if environment protection requires approval).
4. In **Actions → Publish ontology atlas**, inspect the run triggered by the
   merge, or choose **Run workflow** on `main` after enabling Pages.
5. Open the URL on the completed `github-pages` deployment.

Nothing in the workflow changes repository settings, pushes generated files or
creates a `gh-pages` branch. Pages is not enabled just by adding this workflow.

## Automatic build and deployment

`.github/workflows/ontology-atlas-pages.yml` runs on:

- **Pull requests:** tests and builds a downloadable Pages artifact; never deploys.
- **Pushes to `main`:** tests, builds and deploys after a successful build.
- **Manual runs:** builds any selected branch, but deploys only `main`.

The build job has read-only repository permissions. It installs dependencies
from `uv.lock`, refreshes the local graph, runs the Python tests and dependency-free
Node.js tests, then calls:

```bash
uv run --locked python visualisation/build_pages.py \
  --output _site \
  --repository "$GITHUB_REPOSITORY" \
  --revision "$GITHUB_SHA"
```

The staging script independently rebuilds the public projection from canonical
RDF; it does not trust an old `graph.json` and does not modify that checkout file.
The deployment job alone receives `pages: write` and `id-token: write`, uses the
`github-pages` environment, and deploys the uploaded artifact with GitHub's Pages
actions. An in-progress deployment is not cancelled by a subsequent push.

This workflow is independent of the catalogue-observations workflow. It does not
read bucket credentials, download private files, capture publishers or publish
the large OWL/TriG runtime exports. New captures only affect the atlas after their
public RDF metadata is committed to the source tree.

## Public artifact boundary

`build_pages.py` stages an explicit allowlist:

- `index.html`, `style.css`, and the five browser JavaScript modules;
- a freshly generated `graph.json` containing the existing public RDF projection;
- generated `site.json` containing the repository URL and full deployed commit SHA;
- `LICENSE` and an empty `.nojekyll` marker.

It does **not** copy the repository, `.env`, `captures/`, private CSV contents,
`build/` exports, the LTDS ZIP/PDF collection, Python tools, tests or the atlas
backlog. An existing non-empty staging directory is refused rather than reused,
so stale or private files cannot accidentally hitch a ride in the artifact.

The graph still includes public metadata such as distribution addresses and
checksums, just as the local atlas does. This is not a redaction mechanism: review
changes to the canonical RDF before merging them into a publicly deployed branch.

## Links and project-path hosting

All browser asset requests are relative to the atlas page, so the same artifact
works at `/`, `/busbar/` or under a custom domain. There are no site-root-relative
asset paths or client-side routes requiring special Pages fallback handling.

**BUSBAR** links to the repository. The deployed `site.json` makes inspector
source links point to `https://github.com/<owner>/<repo>/blob/<full-SHA>/<file>`:
source citations remain tied to the built revision even after `main` changes.
The footer's input-fingerprint tooltip includes that revision too.

Local development continues to use `visualisation/site.json`, whose source base
is `../`, so inspector links open the local RDF files. The local brand link points
to the Busbar repository. For a fork, the workflow supplies its repository name
when generating deployment metadata.

Three.js **0.170.0** still loads from jsDelivr. Google Fonts are optional, with
local fallbacks. The deployed atlas therefore needs internet access for Three.js;
this setup does not vendor those third-party assets.

## Preview the staged site locally

From a committed checkout, choose a **fresh** output directory:

```bash
uv run --locked python visualisation/build_pages.py --output build/pages
python3 -m http.server 8000 --bind 127.0.0.1 --directory build/pages
# Open http://localhost:8000/
```

The default repository is `piotch/busbar`; use `--repository owner/name` for a fork.
The default revision is the local `HEAD`; `--revision` accepts only a full commit
SHA, not a mutable branch name. Use a committed checkout so the pinned source
links describe the files actually being previewed. To rebuild, choose a new output
directory or explicitly remove the previous generated directory first.

Checks:

```bash
uv run --locked python -m unittest discover -s tests -v
node --test visualisation/*.test.mjs
```

GitHub's reference: [Using custom workflows with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
