# Scheduled public catalogue observations

`.github/workflows/catalogue-observations.yml` validates and tests changes on pull
requests and pushes to `main`/`master`. Only scheduled and manually dispatched runs
access storage or acquire public catalogues. The schedule is daily at **06:23 UTC**,
subject to GitHub's normal scheduling delays. Scheduled workflows run from the
repository's default branch.

## Enable the workflow

1. Push the workflow, Python package and supporting definitions to the repository.
2. Create repository Actions secrets:
   - `BUCKET_ACCESS_KEY`
   - `BUCKET_SECRET_KEY`
   - Optionally `BUCKET_URL` (also supported as a repository variable).
3. Defaults match the read-only-discovered storage configuration:
   - Endpoint: `https://fsn1.your-objectstorage.com`
   - Bucket: `busbar`
   - Prefix: `catalogue-history`
   - Signing region: `fsn1`
4. Override defaults with repository variables `BUCKET_URL`, `BUCKET_NAME`,
   `BUCKET_PREFIX`, `BUCKET_REGION` if required. Use a prefix without leading or
   trailing slashes; give a new archive its own nonempty prefix.
5. Run **Actions → Catalogue observations → Run workflow** and inspect the result
   before relying on the schedule.

The local `.env` is ignored by Git and is **not** sent to GitHub automatically.
It currently has the three credential/configuration names understood by the
workflow. If GitHub CLI is installed and authenticated, an optional local command
is `gh secret set --env-file .env` from the repository root. Review `.env`'s key
names before doing so; do not include unrelated secrets. This setup does not
create bucket policies or make the archive public.

Use dedicated least-privilege credentials for this bucket/prefix. The workflow
needs bucket listing for the history prefixes, object reads, and conditional
object writes; it does not need remote deletion or bucket-administration access.
Hetzner's access/secret keys are used here rather than assuming AWS OIDC support.
Validation has only `contents: read`. The observation job also has `id-token: write`
for the optional [London SSEN relay](ssen-relay.md). Its AWS role can invoke only
the relay; Hetzner bucket authentication is unchanged.

## What a run does

```text
Validate declarations and run offline tests
                ↓
Restore previous archive from the bucket
                ↓
Capture every declared public source independently
                ↓
Persist original responses and observations (including acquisition failures)
                ↓
Build TriG history + OWL viewer
                ↓
If everything succeeded: publish versioned exports, then latest.json
```

An acquisition failure does not stop other DNOs being checked. The workflow still
archives successful captures and failed acquisition records, but reports the run
as failed and does not advance the latest-export index. Restore/storage failures
also fail the job. A failed build cannot advance the index either. Raw history is
persisted before derived exports are built, so an export failure does not discard
new evidence. A later run can retry publishing without altering old observations.

The workflow serializes observation jobs with `cancel-in-progress: false`. Run
only one external writer per bucket prefix as well; the archive is not a distributed
lock service. GitHub may coalesce queued scheduled jobs, so observations are not
guaranteed at exact intervals.

## Bucket layout

```text
s3://busbar/catalogue-history/
  objects/sha256/<hash>.rdf
  observations/<timestamp>-<uuid>.json
  exports/<github-run-id>-<attempt>/
    observations.trig
    news-catalogues.owl
    capture-summary.json
  exports/latest.json
```

History files and versioned export files use conditional create-only writes and
are never intentionally overwritten. Existing content must match before a write
is skipped. The storage provider must support S3 `If-None-Match: *` conditional PUT;
there is no unsafe overwrite fallback. Only `exports/latest.json` is a mutable
pointer; it is updated after all three versioned export files are uploaded.

Each new CI manifest records:

- `artifact_path`: a capture-root-relative path, used to find restored bytes locally.
- `artifact_uri`: the stable `s3://` location of the response object.
- `manifest_uri`: the stable `s3://` location of that observation record.

Builders resolve bytes from the restored capture directory and verify SHA-256;
they do not need live S3 credentials. RDF provenance uses stable storage references,
not the ephemeral runner's filesystem. These are private object identifiers, not
public or presigned download URLs. Authorized consumers can restore history using
`uv run --extra s3 busbar bucket pull` and query or rebuild it locally.

The initial laptop-only captures are not uploaded automatically. Their absolute
`file://` references are not suitable for the shared archive; bucket push rejects
nonportable manifests rather than silently rewriting archived records. The first
CI run starts from the history already in the configured bucket prefix, or starts
a new archive if that prefix is empty.

The workflow also uploads diagnostic build files as GitHub artifacts for 14 days.
Those are convenience downloads, **not the durable archive**. The S3 bucket is the
persistent store. Retention, backup, billing and access policy remain infrastructure
responsibilities; no lifecycle policy is created by this workflow.

## Local commands

`busbar bucket` loads the repository's `.env` without overriding existing
environment variables. Start with `.env.example` and real private credentials.

Read-only credential check (does not test write permission):

```bash
uv run --extra s3 busbar bucket check
```

Restore the shared archive and rebuild (no remote writes):

```bash
uv run --extra s3 busbar bucket pull --captures captures-shared
uv run busbar build-observations --captures captures-shared
uv run busbar build-ontology --captures captures-shared
```

Use a clean restore directory, or an exact previous restore. Conflicting local
files are rejected. `captures-shared/` should stay ignored like `captures/`.

Capture and persist explicitly (these commands **do write to the bucket** at the
push/publish steps):

```bash
uv run busbar capture-all --output captures-shared \
  --storage-uri s3://busbar/catalogue-history
uv run --extra s3 busbar bucket push --captures captures-shared
uv run busbar build-observations --captures captures-shared
uv run busbar build-ontology --captures captures-shared
uv run --extra s3 busbar bucket publish --run-id manual-unique-run-id
```

`busbar capture-all` prints and writes a compact source summary with status, dataset
counts and membership-change counts. Complete observation details remain in the
manifests. No command automatically modifies the curated catalogue, inventory of
private dataset files, Git contents or source definitions.

This first implementation restores and checks the entire history on each run.
An index/incremental restore can be introduced when archive size warrants it.
