# Busbar investigation agent

A manually started, approval-gated runner for stages 2–3 of the
[investigation workflow](investigation-workflow.md): select useful changes,
prepare GitHub issues, inspect supplied data evidence and prepare findings
comments. **No issues, comments or PRs are created just by starting it.**

Stage 1 already runs in CI. Journal/catalogue PRs (stages 4–5), autonomous
publisher downloads and scheduled agent execution remain future work.

## What is implemented

| Component | Responsibility |
|---|---|
| `busbar investigate triage` | Read RDF report, ontology and curated catalogue; read existing GitHub issues; ask Pi to propose at most three investigations. |
| `busbar investigate inspect-data` | Summarise a local CSV, JSON-array or RDF file; optionally compare its shape to a real preserved earlier file. No model or GitHub access. |
| `busbar investigate inspect` | Interpret explicit evidence for one report dataset, incorporating matching issue bodies/comments; draft an issue or findings comment. |
| `busbar investigate apply` | Validate the approved proposal hash/repository, recheck GitHub and create issues/comments. Never push branches, create PRs or merge. |
| `.agents/skills/busbar-investigate/SKILL.md` | Discoverable Pi skill for supervised use of this workflow. A skill is guidance, not an enforcement mechanism. |

The Python package remains model-provider independent. Pi is an optional external
CLI, not a Python dependency. GitHub CLI (`gh`) is used without requiring MCP.
The controller has its own pinned reasoning policy; it does not depend on skill
discovery when running Pi.

## Prerequisites

- Install Busbar's development environment (`uv sync`) and the Pi and GitHub CLIs.
- Configure a model in Pi (for example through its interactive `/login`). Use
  `--model provider/model` on a task to select one explicitly, or Pi's configured default.
- Authenticate `gh` to the intended repository. Planning only needs reads; applying
  needs permission to create issues/comments. No repository-content write permission
  is needed. A dedicated narrowly scoped identity is preferable to a general PAT.
- Have an RDF/XML change report. To fetch bucket latest:

```bash
uv run --extra s3 busbar report-changes \
  --output build/changes.rdf --markdown build/changes.md
```

Bucket access is only needed for that report fetch, not for the investigation
runner once the report is available. An existing CI artifact works too.

## 1. Triage: prepare issue/comment drafts

```bash
uv run busbar investigate triage \
  --report build/changes.rdf \
  --repo piotch/busbar \
  --run build/investigations/triage-001
```

Choose a new run directory each time. The controller refuses to overwrite one,
including a failed or prepare-only run. Optional flags:

- `--max-candidates 1` (up to 3; default 3).
- `--model provider/model`.
- `--timeout 300` (seconds; maximum 900).
- `--prepare-only`: read inputs and GitHub, write the task packet, but do not invoke
  the model or produce an executable proposal.

The task reads existing issues, including closed ones. A relevant open issue
becomes a comment proposal rather than a duplicate issue. Closed or ambiguous
matches stop the proposal: inspect their decisions manually rather than allowing
automatic reopening. Low-value findings may result in no drafts.

The model sees the ontology's concepts, curated dataset titles, report events,
changed statements, snapshots, windows and recurrence uncertainty. This supports
relevance assessment, **not a verified semantic mapping or full catalogue review**.
The runner is not a general coding agent and does not browse publisher pages.

### Run files

```text
build/investigations/triage-001/
  report.rdf          # Exact input copy
  packet.json         # Exact evidence/context sent to Pi
  model-response.json # Parsed response, before action validation (when valid JSON)
  proposal.json       # Validated action list and provenance, if successful
  proposal.md         # Human-readable drafts
  receipts.json       # Result URLs after apply
```

The command prints the SHA-256 of `proposal.json`. **Read both the human draft and
JSON action targets before approving**. Check for unsupported claims, incorrect
source mappings, sensitive information, notifications and links. Review the packet
when you need to understand the evidence provided to the model.

The run directory is local and ignored under `build/`; it is not automatically
uploaded or a durable archive. Copy important evidence to an approved durable
store before relying on it long-term. Never commit private run data by accident.

## 2. Explicitly approve GitHub writes

After review, use the exact hash printed by the preceding command:

```bash
uv run busbar investigate apply \
  --run build/investigations/triage-001 \
  --repo piotch/busbar \
  --approve '<SHA-256-of-reviewed-proposal.json>'
```

This is the **only command here that writes to GitHub**. It can create an issue or
post a comment on the approved matching issue. The repository must match the
proposal. Editing proposal bytes invalidates the old hash; if you edit a draft,
review the entire changed proposal and calculate a new hash before applying:

```bash
python -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("build/investigations/triage-001/proposal.json").read_bytes()).hexdigest())'
```

Apply rechecks issue state and targets. It refuses a closed/ambiguous investigation
or a newly matching issue that would change an approved create into a comment.
Re-plan rather than silently redirecting writes. Approval covers the whole small
batch; actions are sequential, **not an atomic transaction**. A failure can occur
after earlier actions succeeded—check receipts and GitHub before retrying.

Machine markers identify investigations by repository, source catalogue and exact
dataset IRI. Findings additionally identify the report events, task and evidence
hashes. Existing human issues containing the exact dataset IRI are also considered.
Markers are not security tokens: they provide retry/deduplication hints.

On retry, an already posted finding is skipped. Receipts are checkpointed after
each write; marker lookup also recovers from a lost write response. The local run
lock prevents simultaneous applies of that run. **Serialize all applies for a
repository yourself**: GitHub does not offer atomic marker-based issue creation,
and the runner does not provide a distributed/repository-wide lock. A stale
`apply.lock` after a killed process requires manual confirmation that no apply
is active before removing it.

## 3. Inspect a dataset, then prepare findings

Obtain permitted data files separately after checking licence, access conditions,
privacy and size. This version does not follow metadata URLs or download data
automatically. It cannot execute publisher macros or scripts.

Generate a shape summary without including row values:

```bash
uv run busbar investigate inspect-data \
  --input /path/to/current.csv \
  --output build/investigations/substations-shape.json

# Only if an actual earlier file is available:
uv run busbar investigate inspect-data \
  --input /path/to/current.csv --previous /path/to/earlier.csv \
  --output build/investigations/substations-comparison.json
```

Supported: UTF-8 CSV, JSON arrays of objects, Turtle, RDF/XML and N-Triples.
CSV reports field names and row count, JSON also reports observed value types,
and RDF reports predicate/triple counts. Comparison reports added, removed and
changed fields. This is **shape comparison**, not a record-level content diff or
full RDF schema validation. XLSX, ZIP, GIS and other formats need a separately
reviewed extraction step for now. Each input is limited to 20 MiB.

Summaries include file hashes, byte sizes and counts. They do not establish source
URL, edition date or authenticity. Add a short privacy-safe evidence note recording
where/how files were acquired, retrieval time, licence, provenance and any schema
interpretation. Review field names and metadata too: omission of rows is not a
guarantee that all information is safe to publish or send to a provider.

Then interpret the evidence for one dataset present in the report:

```bash
uv run busbar investigate inspect \
  --report build/changes.rdf \
  --repo piotch/busbar \
  --dataset 'https://connecteddata.nationalgrid.co.uk/dataset/d5af0572-6b17-456e-b24f-1a729a91cdbc' \
  --evidence build/investigations/substations-shape.json \
  --evidence /path/to/provenance-notes.md \
  --run build/investigations/substations-001
```

`--evidence` is repeatable, UTF-8 text only, at most 100 KB per file. These exact
extracts are sent to the model, alongside matching issue bodies and comments.
Do not supply raw customer records, credentials or presigned URLs. Inspect needs
at least one explicit evidence file; it cannot pretend a distribution was inspected
from catalogue metadata alone.

Review and apply the resulting findings proposal separately, using its own run
path and hash. A matching open investigation gets a comment; if none exists,
the task may propose a new issue. The report saved with the original investigation
can be reused even when that dataset is absent from today's filtered report.
Always describe its observation window accurately rather than calling it current.

## 4–5. Journal and catalogue PRs

The controller intentionally stops at issues/comments. Once an investigation
justifies a change, use a supervised coding session in a dedicated worktree to
prepare the catalogue patch and usually the journal entry together. Validate,
review and merge through the normal PR workflow. No blog engine is configured
yet and the runner never publishes a post or asserts a decision was accepted.
See the [workflow requirements](investigation-workflow.md#45-publish-and-curate).

## Execution and security boundaries

```text
RDF report + local ontology/catalogue + read-only GitHub context + chosen evidence
                       ↓
Python controller → tool-free Pi reasoning subprocess → validated proposal files
                       ↓
Human reviews exact content and approval hash
                       ↓
Separate apply → GitHub recheck → issue/comment → receipt
```

Pi runs once with tools, extensions, MCP, context discovery, skills, prompt
expansion and session persistence disabled, in a temporary working directory.
The child environment strips GitHub, bucket, AWS and Pi-specific variables. It
retains model-provider credentials and access to normal Pi authentication files.
No raw model diagnostic output is copied into public comments.

**This is not an OS sandbox.** Pi itself still has the account's filesystem and
network permissions; disabling model tools does not isolate the process or erase
credentials stored on disk. For stronger separation run it as a dedicated user or
inside a container exposing only the needed inputs and model authentication.
Do not mount `.env`, SSH keys or GitHub credentials into a reasoning container.

The controller does not shell-interpolate model text. GitHub writes use fixed API
paths, validated targets and JSON stdin. Publisher text, evidence and GitHub
comments are untrusted facts—not commands or authority to change permissions.
The approval hash is a local human workflow gate, not a signature or protection
against an attacker controlling the same local account.

Budgets: at most 200 report datasets, a 500 KB task packet, 3 drafts, a bounded
model response and one time-limited model invocation. Oversized packets fail
rather than being silently truncated. There is **no token/spend accounting or
hard monetary cap** yet; set provider-side limits for unattended use. GitHub reads
have time/output checks and may fail for large repositories. No arbitrary model
tool loops or automatic downloads run in this version.

## Moving beyond the laptop

Keep the same bounded CLI in a container on a server or a manually dispatched
Actions job once the pilot is useful. Use a **separate investigation workflow**,
not broader write permissions on the existing observation job. Separate reasoning
and apply credentials/security contexts and serialize repository writes.

Prefer a narrowly scoped GitHub App installation token for unattended posting.
If later PR automation should trigger normal validation, account for GitHub's
suppression of most workflow events generated using `GITHUB_TOKEN`. Do not run
untrusted PR code with write secrets, particularly via `pull_request_target`.
No scheduler, GitHub App, automated approval, durable investigation uploader or
PR automation has been installed by this implementation.
