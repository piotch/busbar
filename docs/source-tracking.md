# Tracking DNO publishing catalogues

## Boundaries and authority

Busbar now has a small, runnable source-tracking example for UKPN and Northern Powergrid. It does not replace
`catalogue.ttl` or rewrite its existing series and editions.

| Information | Authority | Location |
|---|---|---|
| Vocabulary and curated source configuration | Git | `vocabulary/`, `definitions/` |
| Existing curated cross-DNO catalogue | Git | `catalogue.ttl` |
| Original HTTP response bytes | Immutable capture objects | `captures/objects/sha256/` |
| Acquisition outcomes and observed membership | Runtime observation records | `captures/observations/` |

The last two directories are ignored by Git. On a local machine, disk is the
initial artifact store; production storage, backup, access control and retention
still need to be configured. The observation manifests are a minimal runtime
store, not a requirement to avoid a future Django database or Iceberg tables.

## Declarations

- `vocabulary/publishing.ttl`: the news/source publishing ontology, including curator responsibility.
- `vocabulary/grid-roles.ttl`: local grid-domain organization classifications (SKOS).
- `definitions/organisations/referenceworks.ttl`: the curator organization.
- `definitions/grid/catalogues/busbar.ttl`: Busbar identity, publisher and maintainer.
- `vocabulary/catalogue-view.ttl`: minimal declarations of standard RDF terms for
  offline OWL viewers (not the complete external standards).
- `definitions/grid/uk/dno/ukpn/organization.ttl`: UKPN's source-registry identity.
- `definitions/grid/uk/dno/ukpn/portal.ttl`: portal ownership,
  current platform, homepage and exposed catalogue.
- `definitions/grid/uk/dno/ukpn/catalogue.ttl`:
  source catalogue and an explicit DCAT capture specification.
- `definitions/grid/uk/dno/npg/`: the equivalent organization, portal and catalogue
  declarations for Northern Powergrid.
- `definitions/grid/uk/dno/{spen,ssen,nged,enwl}/`: equivalent declarations
  for SP Energy Networks, SSEN, National Grid Electricity Distribution and Electricity North West.
- `shapes/publishing.ttl`: SHACL constraints for these declarations.

| DNO | Platform | DCAT RDF/XML endpoint |
|---|---|---|
| UKPN | OpenDataSoft | https://ukpowernetworks.opendatasoft.com/api/explore/v2.1/catalog/exports/dcat |
| NPG | OpenDataSoft | https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/exports/dcat |
| SPEN | OpenDataSoft | https://spenergynetworks.opendatasoft.com/api/explore/v2.1/catalog/exports/dcat |
| SSEN | CKAN | https://data-api.ssen.co.uk/catalog.rdf |
| NGED | CKAN | https://connecteddata.nationalgrid.co.uk/catalog.rdf |
| ENWL | OpenDataSoft | https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/exports/dcat |

Run `uv run scripts/capture_all.py` to capture every declared source.
SSEN's frontend is https://data.ssen.co.uk/; RDF is served by its CKAN backend.

The canonical entity path is:

```text
grid/uk/dno/ukpn/catalogue
```

Its RDF identifier is:

```text
https://busbar.example/id/grid/uk/dno/ukpn/catalogue
```

Its prospective state topic is:

```text
grid/uk/dno/ukpn/catalogue/state
```

`busbar.example` is the existing repository's placeholder namespace, not a
resolvable production identity service. Choose a controlled namespace before
external publication. Turtle uses full IRIs for slash-containing identifiers.
The shared path is a stable naming convention, not a substitute for explicit RDF
relationships. Each DNO now has sibling identities `grid/uk/dno/{dno}/portal` and
`grid/uk/dno/{dno}/catalogue`; the catalogue is related to, not nested beneath,
the portal. Definitions live in `portal.ttl` and `catalogue.ttl` next to the
organization declaration.

A software migration changes the platform attribute, not the portal identity.
Only the shorter identities are supported; the initial experimental history was
reset rather than migrated. No broker, retained state publisher or JSON-LD serializer is implemented.

All six DNO groups have shared `org:Organization` identities. Their DNO
classification uses `org:classification` and the local SKOS concept
`grid:DistributionNetworkOperator`, not a publishing-specific OWL class. The
original grid ontology and curated catalogue now reference those same organization
URIs directly; the old uppercase DNO identifiers are not retained as aliases.
Both original and publishing-specific DNO OWL classes are removed. All six
DNOs in the original domain reference data use the shared classification concept.
The broader network/system/transmission operator classes remain domain modelling,
not a dependency of the shared organization declarations. No equivalence to DSO
roles or external grid vocabularies is asserted.

ReferenceWorks is Busbar's publisher and maintainer. Busbar's shared catalogue
identity is declared in definitions, while its 96 curated series and 220 editions
remain in `catalogue.ttl`. Source-capture loading and the flat OWL viewer do not
load that curated membership or the original grid ontology. The TriG history
export includes curated membership in its own named graph. See
[shared foundation](shared-foundation.md).

These files are Busbar's curated assertions, not copies of publisher assertions.
`pub:portalOperator` has an organization range and a publishing-portal domain.
It has no dependency on the original grid ontology's network-area properties. OpenDataSoft and CKAN are software platform resources, not portal
instances. DCAT export format is part of the capture specification, not catalogue
identity.

## Capture lifecycle

```bash
uv run scripts/capture_catalogue.py --validate-only
uv run scripts/capture_catalogue.py
uv run scripts/capture_catalogue.py --output /path/to/runtime-storage
uv run scripts/capture_catalogue.py --spec \
  'https://busbar.example/id/grid/uk/dno/npg/catalogue/captures/dcat'
```

Dependencies are declared in the script's PEP 723 metadata and managed by `uv`.
Python 3.11 or newer is required. The script:

1. Parses all `definitions/**/*.ttl` and `vocabulary/**/*.ttl` files.
2. Validates them with SHACL before any network access.
3. Resolves the selected capture specification (UKPN DCAT by default).
4. Fetches the export with a timeout and 50 MiB total response limit, following CKAN Hydra pagination (up to 1,000 pages).
5. Archives the exact response bytes, deduplicated by SHA-256.
6. Parses RDF/XML and requires a `dcat:Catalog` and IRI-identified dataset entries.
7. Writes a unique observation, even when the response bytes are unchanged.
8. Compares dataset IRIs against the preceding successful observation of this
   specification. It reports `newly_listed` and `no_longer_listed`, not deletion.

Paginated captures preserve each exact response and its HTTP metadata in
the observation's `pages` array. The main artifact is a derived RDF/XML union
(`artifact_kind: rdf-page-union`) so existing viewers and comparisons see the
complete catalogue. Single-page artifacts remain byte-for-byte responses.
Page numbers must advance and are requested on the declared endpoint, even if
Hydra links advertise a different frontend host. Failed pages or a mismatch with
`hydra:totalItems` fail the whole observation, never a successful partial snapshot.

NGED currently publishes malformed IRIs such as `rdf:resource="GIS Data"`.
Raw artifacts are unchanged. The TriG projection resolves these malformed IRIs
against the request URL and percent-encodes illegal characters, recording
`pub:iriRepairCount` on the observation. This is a serialization repair, not
a business-concept mapping.

Observations written with `--storage-uri s3://bucket/prefix` retain portable
`artifact_path`, `artifact_uri` and `manifest_uri` references. Restored files can be
queried on a different machine; local file references remain supported for local
experiments. The bucket workflow does not automatically upload laptop-only history.

Each observation records source URL, request start/completion times, HTTP result,
response content type, ETag/Last-Modified when supplied, artifact URI/hash,
selected specification, Git revision and exact hashes of the effective declaration
files. A Git revision alone would not capture uncommitted declaration edits.
Publisher modification times remain in the original RDF; they are not replaced
with the local observation time.

Network, HTTP and parsing failures produce failed observations and a nonzero exit
code. A response that fails parsing is still archived. Failures do not become
empty catalogues and do not replace the previous successful comparison baseline.
Truncated over-limit responses are rejected rather than archived as complete.
Invalid declarations fail before acquisition; they do not create observations.

Only successful acquisitions of the same capture specification are compared.
A successful export is still a publisher observation, not proof that every
publisher-internal dataset was included. Endpoint/access-policy changes can alter
visibility. If changing the capture scope, use a new specification identity to
avoid comparing unlike scopes.

## What is intentionally not implemented

- Standalone scripts do not schedule themselves. The repository now includes an
  optional GitHub Actions workflow for daily/manual capture with durable bucket
  storage; see [workflow setup](github-actions.md).
- No dataset content download, Django integration, Iceberg loading or UNS publication.
- No native API field-schema or glossary capture yet; DCAT alone does not preserve
  all the useful metadata identified in the UKPN exploration.
- No automatic linking of source dataset entries to existing Busbar dataset series.
- No inference that every capture is a new publisher edition.
- No RDF-semantic change diff. `bytes_changed` is only a byte comparison: XML
  ordering, prefixes and blank-node labels can change without meaning changing.
- No assertion that catalogue absence means a dataset was deleted.
- No distributed coordination. Run one capture per specification at a time;
  overlapping runs can select the same previous baseline.
- No dedicated authentication or credential configuration; the example uses the
  public export endpoint. Do not put secrets in Git declarations.

## Independent news/source viewer export

```bash
uv run scripts/build_ontology.py
open -a "$HOME/Applications/Protégé.app" build/news-catalogues.owl
```

The builder uses the latest successful observation of every declared capture
specification by default. It fails if any selected source has no successful capture,
rather than silently leaving it out. Select sources with repeated `--spec <IRI>`
arguments, or select specific observations with repeated `--observation <path>`
arguments. Change the runtime capture directory with `--captures <directory>`.
It verifies each artifact hash, dataset count and declared catalogue identity
before building the export. Capture-relative artifact paths let restored S3-backed
observations be read locally without fetching remote URIs during the build.

The graph contains the independent vocabulary and current source definitions plus
one selected capture per source, with this exploration path for each DNO:

```text
UKPN ← portalOperator — Portal → exposesCatalog → Catalogue → dataset → Dataset
                                                   ↑                    → distribution → Distribution
                                              observedCatalog
                                                   ↑
                                               Observation
```

The viewer has one canonical source catalogue individual per DNO, plus the
separate Busbar curated-catalogue identity (without its curated membership). All portals reference
the same OpenDataSoft platform resource. Dataset identities and membership stay
publisher-scoped; similarly named datasets or themes are not automatically treated
as equivalent. No cross-DNO business-concept mappings are asserted by this merge.

This is a horizontal collection of catalogues, not a `dcat:DatasetSeries` of
publisher editions. Repeated acquisitions remain separate observations in storage.
The builder rejects two observations of the same specification in one flat export:
otherwise old and new membership would be unioned into a misleading state. Historical
comparison views would need explicit per-snapshot graph boundaries or reified facts.
The selected captures can have different observation times; the combined view is
not an atomic, synchronized observation across publishers.

For each catalogue, source catalogue subject and
object references are rewritten to that identifier only in the derived viewer
graph. The original URI is retained as the `pub:sourceCatalogIdentifier` data
property (an `xsd:anyURI` literal), not as a second catalogue node. Original
catalogue titles/labels are retained as `pub:sourceCatalogTitle` annotations, so
the curated display name remains unambiguous. The builder rejects captures with
more than one catalogue instead of merging distinct catalogues accidentally.

An observation individual links to the canonical catalogue, observation time and
archived artifact using the new vocabulary and PROV-O. Dataset identifiers are
unchanged. The archived response preserves every original byte and statement;
identity normalization and display labels affect only the generated viewer file.
Standard classes and selected object properties are declared locally so Protégé
can display dataset instances and edges without fetching remote vocabularies.
These are a minimal viewer schema, not full DCAT conformance or OWL reasoning
validation. A single merged file also does not preserve named-graph provenance
for each statement; the original capture remains the evidence boundary.

The older `build/busbar.owl` and `build/news-ukpn.owl`, if present, are stale
exports. Open `build/news-catalogues.owl` instead. Generated files remain ignored by Git.

## TriG observation history

```bash
uv run scripts/build_observations.py
# Optional: select particular observation manifests instead of the entire archive.
uv run scripts/build_observations.py --observation <first.json> --observation <second.json>
```

The derived `build/observations.trig` has these named graph boundaries:

- `https://busbar.example/graphs/current-definitions`: current Git-managed
  vocabulary and source definitions, not historical declarations.
- `https://busbar.example/graphs/busbar-catalogue`: current ReferenceWorks-curated
  series membership, editions and distributions from `catalogue.ttl`, not publisher
  claims or observation snapshots. Organization and catalogue identities are
  shared with the definitions graph. The original grid-domain ontology is not
  automatically included.
- `https://busbar.example/graphs/observations`: observation records, canonical
  catalogue identity, specification, acquisition time/status, count, content hash,
  manifest and artifact references, and publisher catalogue identity.
- `<canonical-catalogue>/observations/<observation-id>`: one publisher RDF graph
  per successful observation. The graph identifier is the observation identifier.

Snapshot graphs contain only the parsed publisher statements: no canonical URI
rewrites or added viewer labels. The metadata links each snapshot to the canonical
catalogue with `pub:observedCatalog` and to the publisher's catalogue URI with
`prov:hadPrimarySource`. This deliberately differs from the flattened OWL viewer:
raw source identities and historical graph boundaries must remain explicit here.

Identical bytes still produce separate observation graphs. Blank nodes are scoped
per parse so unrelated observation graphs cannot accidentally share anonymous
resources. Failed acquisitions appear only as observation metadata, not as empty
snapshot graphs. The default graph is empty; queries must select the intended
named graphs. This avoids silently mixing captures or current declarations.

Every successful capture is hash-checked and its dataset count checked; the stored
triple count is also verified when present. An invalid success artifact fails the
build rather than quietly omitting evidence. Existing artifacts/manifests are not
modified. The generated TriG is parsed again to check graph identities and counts
before replacing a previous export. No database is required.

Historical records are not required to match today's capture declarations: a
changed or removed source configuration should not erase old observations.
Original per-acquisition declaration hashes remain in the referenced JSON manifest;
the current-definitions graph does not reconstruct their historical contents.

### Query with RDFLib

From the repository root:

```bash
uv run --with 'rdflib>=7.1,<8' python - <<'PY'
from pathlib import Path
from rdflib import Dataset
history = Dataset(default_union=False)
history.parse('build/observations.trig', format='trig')
for row in history.query(Path('queries/list-observations.rq').read_text()):
    print(row.catalogue, row.observedAt, row.status, row.datasetCount, row.observation)
PY
```

To find newly listed datasets, run `queries/newly-listed-datasets.rq` with the
observation IRIs bound as `before` and `after`:

```python
from rdflib import URIRef
rows = history.query(
    Path('queries/newly-listed-datasets.rq').read_text(),
    initBindings={'before': URIRef(before_iri), 'after': URIRef(after_iri)},
)
```

Reverse the bindings to find datasets no longer listed. The query requires
successful observations of the same catalogue and capture specification. This is
a membership comparison, not a full semantic diff of descriptions or blank-node
subgraphs; RDF-aware graph comparison is needed for that next step.

## Tests

```bash
uv run --with 'rdflib>=7.1,<8' --with 'pyshacl>=0.30,<1' \
  python -m unittest discover -s tests -v
```

Tests use local responses and do not contact UKPN. They cover declaration
resolution, repeated unchanged observations, artifact deduplication, membership
changes, failed requests, invalid RDF payloads and rejection of non-catalogue RDF.

A future Django loader should project these declarations into runtime records,
keyed by the RDF identifiers, rather than treating Django primary keys as source
identity. Git remains authoritative for curated configuration; observations and
captured evidence have a separate lifecycle.
