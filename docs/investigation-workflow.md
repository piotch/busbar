# From observations to reviewed catalogue changes

**Use artifacts for evidence, issues for investigation, comments for progress,
and PRs for proposed changes.** GitHub is the coordination layer for people,
programs and agents; the bucket preserves observation evidence. The journal
explains decisions without becoming a competing catalogue or task tracker.

## Workflow stages

| Stage | Choose | What it contains |
|---|---|---|
| **1. Identify noteworthy updates** | **CI artifact** | Filtered RDF report, Markdown summary, metadata diffs and references to bucket snapshots. Produce this every successful reporting run—even when nothing warrants attention. |
| **2. Select an interesting change** | **Create an issue** | Dataset ID, what changed, relevance to Busbar, evidence links and questions worth investigating. Update an existing investigation rather than duplicate it. |
| **3. Explore in depth** | **Comment on the issue + artifact** | Findings from reading data: schema/shape comparisons, coverage, identifiers, join keys and ontology fit. Keep large outputs in artifacts; summarise conclusions in comments. |
| **4. Publish a journal/blog post** | **Create a PR** | Markdown entry explaining the finding, uncertainties and decision, linked to the investigation. A merged post becomes the public account—not every investigation needs one. |
| **5. Update `catalogue.ttl`** | **Create a PR** | Proposed catalogue changes, evidence and validation results, linked to the investigation explaining their justification. This stage is optional: an investigation may conclude that no catalogue change is warranted. |
| **Across stages: review or revise a proposal** | **Comment on the PR** | Questions and decisions about specific proposed changes. Keep broader investigation on the issue. |

### Decision rule

- Machine output only? **Artifact.**
- Needs attention or investigation? **Issue.**
- Adds evidence to existing work? **Comment.**
- Changes repository content? **PR.**

An observation is evidence, an issue is discussion, and a merged PR is an
accepted repository change. Agent recommendations are not decisions by themselves.

## What exists today

The capture workflow, bucket history and `busbar report-changes` implement stage 1.
The report uses observed catalogue metadata changes, not declared frequencies.
It excludes unchanged datasets and updates also observed changing on the previous
UTC day. Unknown previous-day recurrence remains visible; it is not evidence of
non-routine behaviour. Additions/removals refer to catalogue listings, not dataset
creation/deletion. See [the report documentation](../README.md#observed-dataset-changes).

The report does **not** fetch the listed dataset files, create issues, investigate
contents, publish posts or update the curated catalogue. The
[investigation runner](investigation-agent.md) now supports manually started
triage and evidence-based investigation with separately approved issue/comment
writes. Its local file inspector summarises CSV/JSON/RDF shapes; autonomous
downloads, journal/catalogue PR automation and a blog engine are not configured.
Jekyll with `jekyll-feed` is a possible future GitHub Pages setup.

## 2. Select an interesting change

Read the RDF report, not just its three-column Markdown rendering. The RDF retains
event type, source catalogue, comparison snapshots, observation windows, changed
predicates and recurrence uncertainty.

Assess relevance against `busbar-ontology.ttl` (network model, connections,
capacity, geography and measurements) and existing coverage in `catalogue.ttl`.
A title match is a hypothesis, not a verified mapping. Prefer findings with a
clear question: new distribution, schema change, revised scope, useful join keys,
or an apparent change in a source already tracked by Busbar. A timestamp-only
change can be recorded as low priority without opening an issue.

An investigation issue should contain:

- Publisher, source catalogue and exact publisher dataset IRI.
- Report event and before/after observation identifiers, with durable evidence references.
- **Observed facts**: what metadata changed, and when we observed it.
- **Interpretation**: why this could matter, with explicit uncertainty.
- Questions and a small checklist defining what would resolve the investigation.
- Known access, licence or privacy limitations.

Search both open and closed issues using the dataset IRI and a stable machine
marker. Add a new finding to an existing relevant open investigation. A closed
issue may document a deliberate decision to defer or reject the source: do not
automatically reopen it or create a replacement without assessing that decision.

## 3. Explore in depth

A bounded investigation can:

1. Read the captured description and the publisher's documentation.
2. Identify distributions, formats, access conditions and licences.
3. Download permitted files with size/time limits and record URL, retrieval time
   and SHA-256. A current download is not automatically the edition described by
   an earlier catalogue snapshot.
4. Inspect schemas, worksheets, RDF shapes, coordinate systems, units, key fields,
   coverage and small privacy-safe samples.
5. Compare to a previously preserved **data file**, if one exists. Otherwise report
   the current shape without claiming a historical content or schema change.
6. Evaluate potential ontology mappings and joins to existing curated sources.
7. Comment with findings, evidence, limitations and a recommendation: proceed,
   request human input, defer, or make no change.

Never infer record-level data changes solely from a changed `dct:modified` value.
Do not invent missing schemas, publication dates, identifiers or access rights.
Catalogue snapshots contain metadata, not historical copies of every distribution.
The private archive is not yet connected or verified by this repository.

Large evidence belongs in run artifacts and, where explicitly configured, a
separate durable investigation-evidence store. CI artifacts currently expire
after 14 days. Preserve important facts and hashes in the issue/PR; link to
immutable bucket objects where available, not just `latest.json` or laptop paths.
Private `s3://` identifiers are evidence references, not public download links.
Do not paste credentials, presigned URLs, sensitive rows or private data into
public issues, logs or journal entries.

## 4–5. Publish and curate

Usually combine the **catalogue update and final journal entry in one PR**, so
the explanation matches the accepted change. If the discovery is worth publishing
before a catalogue decision, use a separate journal PR and explicitly describe
it as an investigation. Publication follows merge and successful site deployment,
not PR creation.

A journal entry should explain what was observed, what was verified, what remains
uncertain, what was decided and why. Link to the issue, PR and shareable evidence.
Avoid presenting an unmerged proposal as an accepted decision.

A catalogue PR must respect the existing model:

- Source dataset entries are not automatically identical to curated series.
- Observations are not dataset editions; edition dates need evidence.
- Distribution URLs, formats, licences and archive paths must be justified.
- Never invent a `busbar:localPath` or imply that a remote file was archived.
- Ontology extensions or equivalence claims need explicit review, not silent
  additions to make a dataset fit.

Use a dedicated branch/worktree, keep changes narrowly scoped, and record the
validation commands and results. At minimum run:

```bash
uv run busbar capture --validate-only
uv run python -m unittest discover -s tests -v
```

Also parse the changed RDF and check the affected catalogue structure; source
capture validation alone does not validate every curated catalogue assertion.
Keep merges, public publication and changes to access permissions human-reviewed.

## Example: NGED Distribution Substations

```text
CI artifact: non-routine observed catalogue changes
  → Issue: investigate Distribution Substations
    → Comments + evidence: schema, upstream links, customer/LCT coverage
    → Recommendation: add source, investigate further, or leave catalogue unchanged
    → PR if justified: catalogue.ttl changes + journal entry
      → Human review → merge → journal deployment → close issue
```

Do not open an issue for every row merely because it survived the noise filter.
The filter identifies candidates; selection and investigation establish relevance.
