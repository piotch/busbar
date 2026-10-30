<p align="center">
  <img src="docs/images/busbar.png" alt="Busbar logo" width="240">
</p>

<h1 align="center">Busbar</h1>

Busbar is an open-source catalogue of open datasets about the UK electricity grid. It records where datasets come from, what they describe, their geographic and temporal coverage, and their publication history, using established metadata standards to organise this information.

The project starts from a practical observation: finding a dataset is only the first step towards using it. Grid data is published across many organisations, with different formats, definitions and update cycles. Busbar helps users identify comparable datasets and follow successive publications, providing a clearer foundation for grid modelling, simulation and digital twin projects.

The core catalogue describes those datasets in two standard files, both written in [Turtle](https://www.w3.org/TR/turtle/) (`.ttl`). Curated publishing-source definitions and capture tooling extend this foundation (see below).

| File | What it contains | Standard |
|---|---|---|
| `busbar-ontology.ttl` | The vocabulary: network concepts (substations, circuits, projects…), dataset types, publishers, areas | OWL 2, SKOS |
| `catalogue.ttl` | The datasets: who publishes each one, what it covers, and every edition and file | DCAT 3, Dublin Core |

The ontology defines network concepts such as `busbar:GridSupplyPoint`, and the catalogue uses them. All six DNO publisher references now reuse the shared organization identities under `definitions/`, rather than separate uppercase identifiers.

![Historical Busbar ontology and catalogue map](docs/images/busbar-map.png)

*Historical diagram of the initial domain model and catalogue. It predates the shared organization identities and ORG/SKOS DNO-classification changes and is not an exact representation of the current ontology.*

## Architecture at a glance

![DNO catalogue observations and Busbar's curated archive catalogue](docs/images/catalogues-and-archives.svg)

For a changeset handover, see [catalogues, observations and archives](docs/catalogues-and-archives.md).
It distinguishes implemented source observation from future archive/source mappings.

## Shared organizations and catalogue identities

- All six GB DNO groups are `org:Organization` instances, classified as DNOs
  through `org:classification` and the local SKOS scheme in `vocabulary/grid-roles.ttl`.
- ReferenceWorks is defined in `definitions/organisations/referenceworks.ttl`.
- ReferenceWorks publishes and maintains Busbar, whose identity is defined in
  `definitions/grid/catalogues/busbar.ttl`.
- Busbar's series membership, editions and distributions remain in `catalogue.ttl`.
  Its catalogue identity is `https://busbar.example/id/grid/catalogues/busbar`.
- DNO source catalogues keep their separate identities under
  `grid/uk/dno/{dno}/catalogue` and their publisher responsibilities.

See [shared foundation](docs/shared-foundation.md). No curated ECR-to-source mapping
or DNO/DSO equivalence has been asserted yet.

## Viewing in Protégé

Generate an independent RDF/XML ontology containing the news/source vocabulary,
source definitions and the latest successfully captured DCAT catalogues for all six DNOs. Shared identities, including Busbar and ReferenceWorks, are included.
The original grid-domain vocabulary and Busbar's curated series membership are
not merged into this flat viewer file:

```bash
uv run scripts/build_ontology.py
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
uv run scripts/build_observations.py
```

This writes ignored `build/observations.trig`: one named graph per successful
capture, an observation metadata graph, a current-definitions graph, and a separate
Busbar curated-catalogue graph. These can be queried together without merging
publisher assertions with curator assertions.
Repeated observations remain separate even when their content is identical.
Failed acquisitions have metadata but no snapshot graph. Original publisher
identifiers are preserved inside each snapshot; canonical source identities are
linked through the metadata, not merged across historical states.

See [source tracking](docs/source-tracking.md#trig-observation-history) for
SPARQL examples. Protégé's flat OWL export remains a separate viewer artifact.

## Scheduled capture with GitHub Actions

The [Catalogue observations workflow](.github/workflows/catalogue-observations.yml)
can capture public catalogues daily and on manual dispatch, persisting history in
the S3-compatible bucket and publishing versioned exports. Pull requests only run
validation and tests; they never access bucket credentials.

Configure the repository secrets first—the local `.env` is not available on a
GitHub runner. See [GitHub Actions setup and storage](docs/github-actions.md).

## Tracking publishing sources

Git-managed Turtle declarations describe UKPN, Northern Powergrid, SP Energy Networks,
SSEN, National Grid Electricity Distribution and Electricity North West, their
OpenDataSoft or CKAN portals, source catalogues and DCAT capture endpoints. Their canonical
paths follow `grid/uk/dno/{ukpn|npg|spen|ssen|nged|enwl}/catalogue`, shared with
the intended UNS. Each source catalogue is distinct from Busbar's curated catalogue above.

With [uv](https://docs.astral.sh/uv/) installed, run from this repository:

```bash
# Validate the declarations without accessing the network.
uv run scripts/capture_catalogue.py --validate-only

# Capture all six declared sources.
uv run scripts/capture_all.py

# Or capture UKPN (the default) and Northern Powergrid separately.
uv run scripts/capture_catalogue.py
uv run scripts/capture_catalogue.py --spec \
  'https://busbar.example/id/grid/uk/dno/npg/catalogue/captures/dcat'
```

Original responses and observation records are written under ignored `captures/`,
not committed to Git. Run a capture command again to compare catalogue membership
with the previous successful observation of that same specification. Standalone
commands are unscheduled; the GitHub workflow runs after repository setup.

See [source tracking](docs/source-tracking.md) for ownership, storage, limitations,
validation and the relationship to Django and the UNS.
