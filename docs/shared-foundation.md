# Shared organizations and catalogue identities

## Canonical identities

All identities use the repository's existing placeholder base
`https://busbar.example/id/`. A controlled public base is still needed before
external publication.

| Entity | Canonical path |
|---|---|
| ReferenceWorks | `organisations/referenceworks` |
| Busbar curated catalogue | `grid/catalogues/busbar` |
| UKPN | `grid/uk/dno/ukpn` |
| UKPN portal | `grid/uk/dno/ukpn/portal` |
| UKPN source catalogue | `grid/uk/dno/ukpn/catalogue` |
| Northern Powergrid | `grid/uk/dno/npg` |
| Northern Powergrid portal | `grid/uk/dno/npg/portal` |
| Northern Powergrid source catalogue | `grid/uk/dno/npg/catalogue` |
| SP Energy Networks | `grid/uk/dno/spen` |
| SSEN | `grid/uk/dno/ssen` |
| National Grid Electricity Distribution | `grid/uk/dno/nged` |
| Electricity North West | `grid/uk/dno/enwl` |

Each DNO has sibling `/portal` and `/catalogue` identities, and a
`/catalogue/captures/dcat` capture specification.

These entity paths also provide the intended UNS addressing convention, with
communication suffixes such as `/state`. No broker integration is implemented.

## Organization classifications

Shared organizations are `org:Organization` instances. All six DNO groups use
`org:classification grid:DistributionNetworkOperator`, where the latter is a
SKOS concept in `vocabulary/grid-roles.ttl`, not an OWL class belonging to a
catalogue vocabulary. This local domain classification makes no claim of exact
equivalence to DSO, CIM, or another external role. Its definition is now grounded
in Annex 2 v7 of LTDS Grid Modelling v2-1-1, section 6, page 75, through a
bibliographic `dct:source` reference. See [CIM/LTDS alignment](cim-ltds-alignment.md)
for the evidence and the pending review of the wider grid-domain ontology.

Both `busbar:DistributionNetworkOperator` and `pub:DistributionNetworkOperator`
OWL classes are removed. All six DNOs in the original domain reference data are
organizations/network operators classified with the same grid SKOS concept.
The domain model's `operates`/`operatedBy` properties now use the broader
`busbar:NetworkOperator` class; DNO classification is stated separately rather
than inferred from those properties. `busbar:Organisation` specializes
`org:Organization`. All six DNO groups' domain facts use the shared organization URIs;
their publisher references in the curated catalogue use the same URIs too.
Non-DNO organizations present only in the original domain model have not been migrated.

## Responsibility, not ownership

`dct:publisher` identifies the organization publishing a catalogue.
`pub:maintainedBy` is an explicitly local property for maintenance responsibility;
it does not assert copyright ownership or authorship of every listed dataset.

- UKPN publishes the UKPN source catalogue.
- NPG publishes the NPG source catalogue.
- ReferenceWorks publishes and maintains Busbar.
- ReferenceWorks is not asserted to publish or maintain any DNO's source catalogue.

Busbar is a `pub:CuratedCatalog`, not a `pub:TrackedCatalog`. It does not need
a remote capture specification. SHACL validates organization names, publisher
references and curator responsibility separately from acquisition configuration.

## Assertion boundaries

- `definitions/`: shared curated identities and responsibilities.
- `catalogue.ttl`: Busbar-curated dataset series, editions and distributions.
  Catalogue name, description, publisher and maintainer live in
  `definitions/grid/catalogues/busbar.ttl`.
- `busbar-ontology.ttl`: the original domain vocabulary and richer reference facts.
- Captured snapshot graphs: publisher assertions, with malformed IRIs repaired only
  in the TriG projection as documented in [source tracking](source-tracking.md).
  Raw response artifacts remain unchanged.
- Observation metadata graph: local acquisition outcomes and evidence references.

The OWL viewer includes definitions and selected source captures, but not the
curated series membership or the original domain vocabulary. Thus it shows seven
catalogue identities: six source catalogues and Busbar.

The TriG export keeps current curated catalogue assertions in
`https://busbar.example/graphs/busbar-catalogue`, separate from current definitions,
observations and source snapshots. Join graphs explicitly using their shared
entity URIs. The current curated graph is not a historical reconstruction of
Busbar at each capture time.

Publisher-assigned organization identifiers in raw DCAT remain unchanged. They
are not automatically equated to curated organization identities. No ECR series
is yet linked to a particular publisher entry; scope and evidence must be reviewed
before adding those mappings.

## Query

`queries/list-catalogues.rq` lists the seven canonical catalogue identities and
their publishers and maintainers from the current-definitions graph:

```bash
uv run scripts/build_observations.py
uv run --with rdflib python - <<'PY'
from pathlib import Path
from rdflib import Dataset
history = Dataset(default_union=False)
history.parse('build/observations.trig', format='trig')
for row in history.query(Path('queries/list-catalogues.rq').read_text()):
    print(row.title, row.publisherName, row.maintainerName)
PY
```

The existing curated series can then be queried in their own graph and joined to
definitions through `dct:publisher` and the shared organization URI.
