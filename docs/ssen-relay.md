# London SSEN relay

SSEN returned 403 from GitHub-hosted capture runners but 200 from a London Lambda.
The optional relay changes acquisition transport, not ontology declarations.
Only `https://data-api.ssen.co.uk/catalog.rdf` (optionally a positive integer
`page` query) is allowed, including redirects. There is no public endpoint.

## Deploy from London CloudShell

These commands **create billable AWS resources**: a Lambda, execution role,
GitHub invocation role, log group and (unless supplied) GitHub OIDC provider.
SAM also creates/uses a deployment S3 bucket. No VPC/NAT gateway is needed.

Use the intended workload account, not the organization management account.
The deploying identity needs CloudFormation, Lambda, IAM, logs and deployment
S3 permissions. Check the repository's default branch; the trust policy allows
only the exact configured repository and branch, not pull requests or forks.

Get the checkout containing these changes into CloudShell (push your branch first,
then clone and check it out, or upload a source archive). From its root:

```bash
aws sts get-caller-identity
sam --version
sam validate --template-file infra/ssen-relay/template.yaml --region eu-west-2
sam deploy --guided \
  --template-file infra/ssen-relay/template.yaml \
  --stack-name busbar-ssen-relay \
  --region eu-west-2 \
  --capabilities CAPABILITY_IAM
```

No build is necessary: this handler uses only Python's standard library.
If SAM isn't installed in CloudShell, follow the
[AWS SAM installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).
For a working local login, append `--profile busbar` to deployment commands.

Guided deployment:
- Region: **eu-west-2** (the template itself does not enforce the region).
- GitHubSubjectPrefix: `repo:piotch@5766816/busbar@1400768869` for this repository;
  branch: your trusted default branch (default `main`).
- Confirm the exact prefix with
  `gh api repos/piotch/busbar/actions/oidc/customization/sub` on your Mac.
  This repository uses immutable subjects containing owner/repository IDs, not
  the legacy `repo:piotch/busbar` prefix. For another repository, use its returned
  `sub_claim_prefix` (or `repo:OWNER/REPO` if it uses legacy default subjects).
- Confirm the change set before execution.
- Allow SAM to create IAM roles; no public invocation is required.
- Save configuration locally if desired; generated SAM configuration is ignored.

If this account already has a GitHub OIDC provider, supply its ARN through
`ExistingGitHubOidcProviderArn`; AWS permits only one provider for that URL.
Do not delete an existing provider used by other applications.

The handler is deployed from `src/busbar/` but imports no package dependencies.
No reserved concurrency is configured, so the function uses the account's shared
concurrency quota (compatible with small new-account quotas).

## Test before enabling GitHub

Read the CloudFormation stack outputs:

```bash
aws cloudformation describe-stacks --stack-name busbar-ssen-relay \
  --region eu-west-2 --query 'Stacks[0].Outputs'
```

Use the returned RelayFunctionArn:

```bash
aws lambda invoke --region eu-west-2 \
  --function-name '<RelayFunctionArn>' \
  --cli-binary-format raw-in-base64-out --payload '{}' /tmp/ssen-relay.json
python3 - <<'PY'
import base64, json
from pathlib import Path
r = json.loads(Path('/tmp/ssen-relay.json').read_text())
print("Upstream HTTP:", r["status"])
print("Bytes:", len(base64.b64decode(r["body_base64"], validate=True)))
PY
```

Expect HTTP 200 and roughly 1 MB. Lambda Invoke's own StatusCode 200 alone does
not establish upstream success; check FunctionError and the response payload.

## Enable GitHub

Set repository **Actions variables**, not secrets:
- `BUSBAR_SSEN_RELAY_FUNCTION`: RelayFunctionArn output.
- `BUSBAR_SSEN_RELAY_ROLE_ARN`: GitHubRoleArn output.
- `BUSBAR_SSEN_RELAY_ACCOUNT_ID`: deploying AWS account's 12-digit ID.

The observation job requests an OIDC token and assumes the invocation role.
Validation/PR jobs do not receive AWS credentials. The role can only invoke this
one function. Existing Hetzner bucket credentials remain independent.

Run the catalogue-observations workflow manually on the trusted branch and
inspect SSEN's result. Authentication failure stops the job; relay failure records
a failed acquisition, without silently falling back to GitHub's network.

## Local behaviour and provenance

Without `BUSBAR_SSEN_RELAY_FUNCTION`, all captures stay direct and need no AWS SDK.
For an explicitly relayed local capture, establish AWS credentials first, then:

```bash
AWS_PROFILE=busbar BUSBAR_SSEN_RELAY_FUNCTION='<RelayFunctionArn>' \
  uv run --extra s3 busbar capture \
  --spec https://busbar.example/id/grid/uk/dno/ssen/catalogue/captures/dcat
```

The existing optional `s3` extra supplies boto3; capture does not load `.env`.
Original source/final URLs, status, selected response headers and exact body bytes
are preserved. The manifest's `acquisition` records Lambda transport, region and
function ARN, including failed invocations. Existing RDF exports retain their
source provenance; transport details are available in the JSON manifest.

Responses are limited to **4 MiB per page**, leaving room for base64 and metadata
under Lambda's 6 MB synchronous response limit. Oversized responses fail visibly.
There is no public proxy, arbitrary URL fetching, data-bucket access, or stored
GitHub AWS access key.

## Costs and removal

Invocation volume is tiny, but billing still applies to Lambda, logs and deployment
storage. Set a budget alert (not a hard spending cap). Logs retain 14 days.

To disable routing, remove `BUSBAR_SSEN_RELAY_FUNCTION` from repository variables.
Remove the SAM stack with `sam delete --stack-name busbar-ssen-relay --region eu-west-2`.
Review deletion prompts and shared OIDC-provider dependencies first. Delete the
manual `busbar-ssen-test` function separately after the managed relay succeeds.
