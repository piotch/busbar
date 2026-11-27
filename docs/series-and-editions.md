# Series and editions

A **series** is a publisher dataset we choose to follow over time, such as ENWL's
Embedded Capacity Register. An **edition** is one version of its file that we
hold. Only ENWL's ECR (part 2, 1 MW and above) is followed so far.

## Who writes what

```mermaid
flowchart LR
    you([You]) -->|choose| D["definitions/…/series.ttl<br/>tracked dataset page"]
    D --> C[busbar capture-series]
    P[(Publisher portal<br/>OpenDataSoft API)] -->|title, update date, file| C
    C -->|writes| E["editions/…/ecr.ttl<br/>publisher's title, latest-file address,<br/>editions and their checksums"]
    C -->|stores| S[("captures/series/<br/>files and run records<br/>local, never in Git")]
```

- `definitions/` holds only decisions: which dataset page a series follows
  (`pub:tracksSourceDataset`). A `dct:title` may be added there to override the
  publisher's, but none is needed. Nothing there is
  rewritten by a program.
- `editions/` mirrors the `definitions/` tree and is written only by Busbar
  commands. Hand edits are lost at the next capture. Each file reads in order:
  the series and its latest-file address, then its editions from oldest to newest,
  each followed by its file.
- Files can hold personal data. They stay in `captures/series/objects/sha256/`,
  named by checksum, and are never committed, sent to the bucket or exported.

## Declaring a series

```turtle
<https://busbar.example/id/grid/uk/dno/enwl/series/ecr>
    a dcat:DatasetSeries ;
    pub:tracksSourceDataset <https://electricitynorthwest.opendatasoft.com/explore/dataset/enwl-embedded-capacity-register-2-1mw-and-above/> ;
    dcat:theme grid:DistributionProject1MWAndAbove .
```

`dcat:theme` says what the records are about, using the project types of
`vocabulary/grid-concepts.ttl`:

```text
Project
├─ Distribution project ("ECR project")
│  ├─ Distribution project, 1 MW and above   (threshold included; ENWL ECR part 2)
│  └─ Distribution project, below 1 MW       (ENWL ECR part 1)
└─ Transmission project ("TEC project")
```

Definitions come from `busbar-ontology.ttl`. These are local concepts: no CIM or
LTDS equivalence is asserted yet.

From the dataset page the capture derives:

- the portal, by matching the page's host with a declared portal's homepage; this
  gives the publisher and the name of the environment variable holding the API key
  (`pub:apiKeyVariable`, here `ENWL_API_KEY`);
- the OpenDataSoft metadata address
  `https://<host>/api/explore/v2.1/catalog/datasets/<id>` and the CSV export
  `…/<id>/exports/csv?use_labels=true`.

The key is only sent over HTTPS to a declared portal, and redirects are refused.
Only OpenDataSoft dataset pages are understood so far.

## What a capture does

`uv run busbar capture-series` (needs the key in the environment or `.env`):

1. Reads the publisher's metadata: title, update date, row count.
2. Records the publisher's title, the publisher and the latest-file address on
   the series in `editions/`. A declared title replaces the publisher's. The
   publisher's description is not recorded: on ENWL it is mostly portal
   boilerplate (disclaimers, sign-in links), and catalogue captures already keep
   it verbatim.
3. Stops there if the update date equals the last edition's.
4. Otherwise downloads the CSV, stores it, re-reads the metadata and fails if the
   date changed meanwhile or if the row count differs from the announced one.
   Without access, OpenDataSoft answers with the header row only.
5. Adds an edition only if the file's checksum is new. Editions are named after the
   publisher's update date, for example `…/enwl/editions/ecr/2026-10-20`.

Every run, successful or not, writes a JSON record in `captures/series/observations/`.

## File schemas and checks

A file's layout is a decision, so it lives in `definitions/`, in W3C
[CSVW](https://www.w3.org/TR/tabular-metadata/): for ENWL,
`definitions/grid/uk/dno/enwl/schemas/ecr.ttl`.

- Only the columns Busbar uses are declared, found by title in any order; the
  others are ignored, so their changes need no new version.
- A version (`…/schemas/ecr/v1`) lists its columns and the "no value" markers
  (`csvw:null`). Columns belong to their version (`…/v1/columns/<name>`). When a
  declared column changes, add a version (`dcat:previousVersion`); never edit
  one in use.
- Each column has its header (`csvw:titles`), its type (`csvw:datatype`) and the
  concept it is about (`dct:subject`), whose `skos:notation` is the standard
  name (concepts in `vocabulary/grid-attributes/project.ttl`).
- `csvw:required true` forbids empty cells; `sh:in` (SHACL) lists the allowed
  values as written in the file.
- A numeric column states the unit the publisher writes in, with `qudt:hasUnit`
(for example `unit:KiloV` or `unit:MegaV-A`). Coordinate columns also name their
reference system with `dct:conformsTo`, as in GeoDCAT-AP; ENWL eastings and
northings are British National Grid (`EPSG/0/27700`), in metres. The check does
not use these: they describe the file, they do not test it. What it does test is
`sh:minInclusive` / `sh:maxInclusive`: eastings must lie within 0–700 000 and
northings within 0–1 300 000, the extent of the grid.

`uv run busbar check-edition <file.csv>` checks a file against the schema,
ignoring case and repeated spaces in titles, null markers and values. It only
reads, prints a JSON report and exits with 1 if the file does not conform; what
to do then is the pipeline's decision.

A series names the schemas its files are checked against with `pub:fileSchema`
in its declaration. At every run, `capture-series` checks each stored edition
file of the series against those schemas only, and records
`dct:conformsTo <schema version>` on each file that conforms, in `editions/`.
Another publisher's file can share the same column titles; it is never checked
against this series' schemas. A schema or check that fails is reported as
`conformance_error` in the observation and leaves the recorded statements as
they were; it never stops a new edition from being archived.

Allowed numeric values are compared by value, so `11.0` matches `11`. A file
that is empty or not UTF-8 gets a report with `conforms: false` and an `error`.

## Querying

`busbar build-observations` puts everything under `editions/` in the
`https://busbar.example/graphs/editions` named graph, apart from declarations.
Join it to the definitions graph through the series URI.

## Not yet done

- Recording the publisher's update date that was last seen, so that a new date
  with unchanged content does not trigger a download at every run.
- Portals other than OpenDataSoft, and publishers listing one file per month (NPG).
