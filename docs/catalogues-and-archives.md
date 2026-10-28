# Busbar: catalogues, observations and archives

![Publisher catalogues and observations, Busbar's curated catalogue and private archive, and the Grid domain ontology](images/catalogues-and-archives.svg)

## The short explanation

**We observe what DNOs publish; we curate what we know about selected datasets.**
These are complementary activities, not two competing catalogues.

| | DNO source catalogues | Busbar curated catalogue |
|---|---|---|
| Publisher | UKPN, Northern Powergrid, etc. | ReferenceWorks |
| Purpose | Describe what a DNO currently exposes | Describe selected series, editions and files we track |
| History | Repeated observations of catalogue metadata | Successive dataset publications described in our inventory |
| Evidence | Captured DCAT response and acquisition record | Archived files and the evidence supporting our descriptions |
| Current storage | Ignored `captures/` directory | Git-managed `catalogue.ttl`; actual private data files live elsewhere |

**A catalogue snapshot is metadata, not a copy of all the data it lists.**

The diagram also shows the **Grid domain ontology**: business concepts and
relationships such as network operators, substations, connections, projects and
capacity assessments. This is distinct from catalogue metadata and archived
files. Mappings from dataset contents to these concepts are not yet implemented;
CIM/LTDS alignment remains under review.

## 1. DNO catalogues and observations

Each DNO has a shared organization identity, a portal and a source catalogue:

```text
grid/uk/dno/ukpn
grid/uk/dno/ukpn/portal
grid/uk/dno/ukpn/catalogue
```

The portal's current software is an attribute (OpenDataSoft in our two examples),
not part of its permanent identity. The catalogue contains dataset descriptions,
export links and sometimes links to historical files.

A capture creates an **observation**: when the catalogue was requested, whether
acquisition succeeded, and which original response was preserved. Repeated checks
are separate observations even if the response bytes are identical. Failed requests
are recorded but never interpreted as empty catalogues.

This lets us ask **"What did the publisher expose when we looked?"** and compare
catalogue membership. Full semantic metadata comparison and dataset-content
comparison are not yet implemented.

## 2. Busbar and the private archive

ReferenceWorks is the publisher and maintainer of Busbar. The existing curated
model is retained:

```text
Busbar catalogue
  → DatasetSeries: UKPN ECR
      → Dataset edition: a particular publication
          → Distribution: a particular file representation
              → private archive file, referenced by localPath
```

The existing catalogue already describes ECR histories across DNOs. Those records
are not replaced by source observations. For example, our private archive can
contain UKPN ECR releases that the current UKPN catalogue no longer exposes.

The catalogue currently records local paths, but those paths do not resolve from
this repository checkout. **We have not yet connected and verified the private
archive's storage root, file identities or acquisition provenance.** Edition-date
meaning also needs review; a filename date is not automatically a publication date.

A publisher can expose multiple historical editions in one observation (as NPG
ECR does through monthly XLSX links). Conversely, many observations can show the
same edition. Observations and editions must not be treated as interchangeable.

## 3. How the two sides will connect

The dashed source-to-series link in the diagram is **future reviewed mapping**,
not implemented synchronization:

```text
Observed publisher dataset entry
             ↕ reviewed source relationship, not automatic identity equivalence
Curated Busbar dataset series
             → editions and file descriptions
```

We must first confirm dataset scope (for example ECR capacity thresholds), date
meaning and whether files are original publisher releases or transformed copies.
Matching titles or months is not enough. No ECR mappings, automatic archive import,
or automatic download of the listed dataset distributions have been implemented.

## 4. What this changeset introduces

- **Shared identities:** UKPN/NPG publisher references in the existing catalogue
  and domain model now use the same organization URIs as the source definitions.
- **Explicit responsibility:** ReferenceWorks publishes and maintains the Busbar
  catalogue, separately from the DNOs' publisher responsibilities.
- **Source registry:** Git-managed Turtle definitions for organizations, portals,
  catalogues and capture specifications, with SHACL validation.
- **Observation tooling:** manually invoked DCAT capture, immutable response
  objects, acquisition records and per-source membership comparisons.
- **Queryable history:** TriG export with separate named graphs for current
  definitions, current Busbar catalogue assertions, observation metadata and
  each successful publisher snapshot.
- **Viewer export:** OWL containing shared definitions and selected source
  captures. It does not load the existing grid-domain ontology or Busbar's
  curated series membership.

The original 96 curated series and 220 editions remain. Busbar catalogue name,
description, publisher and maintainer are now defined under `definitions/`; series
membership and edition descriptions remain in `catalogue.ttl`.

## Vocabulary change worth reviewing

DNO classification is no longer an OWL class owned by the catalogue vocabulary.
Organizations use W3C ORG with a local SKOS classification grounded in the LTDS
v2-1-1 glossary. The old `busbar:DistributionNetworkOperator` and
`pub:DistributionNetworkOperator` classes were removed. The original domain
model's `operates`/`operatedBy` properties now refer to the broader
`busbar:NetworkOperator`; DNO classification is explicit and separate.

Existing queries using `id:UKPN`, `id:NPG`, `id:busbar` or those old DNO classes
must be updated. No compatibility layer is retained in this experimental stage.
The rest of the grid-domain ontology still needs CIM/LTDS alignment review; no
substation, project or capacity equivalence mappings are being claimed.

## Useful entry points

- [Shared foundation](shared-foundation.md): identities, responsibilities and graph boundaries.
- [Source tracking](source-tracking.md): commands, storage and SPARQL examples.
- [CIM/LTDS alignment](cim-ltds-alignment.md): cited DNO definition and pending domain review.

The raw captures, generated exports, private archive data and locally excluded
LTDS reference package are not part of the Git changeset. A subsequent
[GitHub Actions workflow](github-actions.md) now supports scheduled public capture
once repository secrets are configured. No UNS messages are published yet.
