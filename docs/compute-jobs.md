# Compute jobs: plan

Status: **proposed**, awaiting the owner's approval. Nothing on this page is
built, and no AWS resource exists for it.

This repository builds a shared SkyPilot API server on the owner's AWS
account, its admin code, and the client package that projects pin, so that
agents and people can run long jobs (GPU simulation, evolutionary search over
simulations, and ordinary ML training) without knowing SkyPilot or AWS. The
plan is adapted from the
[template's plan at `0a2f134`](https://github.com/arjunbhargava/foundation/blob/0a2f134ea7d5ccaf8d6bfe5f598dcc273f2049e2/docs/compute-jobs.md),
which states SkyPilot facts for 0.14.0 from its documentation, read on
2026-10-15. Facts added on this page cite their source, read the same day;
anything else is marked unverified. Prices are AWS on-demand list prices in
`us-east-1`; the account's negotiated rates are lower and unknown, so every
cost below is an upper bound.

## What the template owns

The template repository's
[PR #76](https://github.com/arjunbhargava/foundation/pull/76) (head
`005a71a`) holds the integration, and nothing on this page builds it:

- the `compute-jobs` skill and the `compute-cost` rule's update;
- the variables' names in `.env.example`;
- the pin of this package in `mise.toml`;
- `mise run job:dry-run|launch|observe|cancel`, which run
  `.github/scripts/compute_job.sh`, which calls this package's `compute-jobs`;
- a Copier question, `compute`, default off (deferred there).

Everything else is here: the server, the admin policy, the limits and
hardware profiles, the IAM policies, provisioning and admin tasks, the
`compute-server-admin` skill, and the client package with the in-job wrapper,
the run record, the archive and `progress.json` formats, and the job image.
[Interface](#interface-contract-v0) is the contract between the two.

## What a user sees

A user describes a job in a small file, checks it, launches it, and watches
it. Nothing starts a machine except `job:launch`, and every job stops itself
at its maximum run time.

```text
$ mise run job:dry-run -- jobs/search.yaml
jobs/search.yaml: kind search, profile gpu-sim, 2 nodes (16 L40S GPUs)
Maximum cost: 2 × $30.13/h × 3 h = $180.78 (list price), within budget_usd 200
Smoke test on this machine's CPU (COMPUTE_JOB_SMOKE=1): 2 generations, 20 evaluations, exit 0
Ready to launch.

$ mise run job:launch -- jobs/search.yaml
Launched pr81-search-3f9a2c1d. Watch it with:
  mise run job:observe -- pr81-search-3f9a2c1d

$ mise run job:observe -- pr81-search-3f9a2c1d
Job pr81-search-3f9a2c1d: RUNNING for 1 h 12 min of 3 h; cost so far about $72 (list price)
Progress: generation 12 of 50, evaluating, 6,400 of 10,000 evaluations; best fitness 0.873
```

| You see | What it means | What to do |
|---|---|---|
| `SKYPILOT_API_SERVER_ENDPOINT is not set ...` | This machine isn't connected to the job server | Ask the owner for the two secrets; never start a server |
| `profile gpu-sim allows at most 2 nodes` | The job asks for more than the limits allow | Ask for fewer, or ask the owner to raise the limit |
| `maximum cost $180.78 exceeds budget_usd 150` | The job could cost more than it may | Shorten `max_runtime_minutes`, use fewer nodes, or raise `budget_usd` within the task's budget |
| `FAILED (exit 1)` in observe | The job's command failed | Read the log tail observe prints, fix, push, launch again |
| `RECOVERING` in observe | AWS took a spot machine back; the job restarts from its last checkpoint | Nothing, if the job checkpoints |
| `driver supports CUDA 12.4, image needs 12.8` | The machine's GPU driver is older than the image | Ask the owner |

## Terms

- **API server**: SkyPilot's server, which holds the AWS credentials and the
  table of managed jobs, and does the launching. A **client** is SkyPilot's
  CLI or SDK pointed at it; here, always through `compute-jobs`.
- **Managed job**: a SkyPilot job that the server watches, relaunching it
  after a spot preemption and deleting its machines when it ends.
- **Job file**: a YAML file in a project's `jobs/`, giving the job's kind,
  profile, command, run time, and budget.
- **Job kind**: `single`, `multi-node`, or `search`.
- **Hardware profile**: a named machine choice, such as `gpu-sim`, that the
  admin maps to instance types in `limits.yaml`.
- **Job name**: `pr<PR number>-<job file name>-<first 8 hex digits of the job
  file's SHA-256>`, such as `pr81-search-3f9a2c1d`.
- **Job archive**: what a job writes to S3 (run record, progress, result,
  output, and log), so results outlive the server.
- **Admin**: the person who provisions and runs the server, with the
  `compute-server-admin` skill. Agents are clients only.

## Why one shared server

Workers and orchestrators run on separate VMs with no shared state, and must
see every job, including one launched by an agent that has since stopped.
SkyPilot keeps its job table on the machine that runs the API server, so
without a shared server no other machine sees a job.

| | (a) Job writes its record to S3 | (b) Shared API server | (c) Managed jobs, no shared server |
|---|---|---|---|
| Who sees a job | Anyone with a read-only S3 key | Every client | Only the launching machine |
| What an agent holds | A read-only S3 key | An endpoint and a token | AWS launch credentials |
| Limits enforced by | A workflow's validation | The server's admin policy, on every request | Nothing central |
| Spot recovery | None | Automatic | Automatic |
| Standing cost | About $1 a month | About $460 a month | A controller VM while jobs run |

**Decided: (b), with (a)'s archive.** The server gives every agent the same
view, enforces limits, and recovers preempted jobs; the archive keeps results
and progress while the server is down. With a remote server, SkyPilot runs the
managed-job controller inside it ("consolidation mode"), so (c) becomes part
of (b).

## The API server

**Where it runs.** SkyPilot's Helm chart on Amazon EKS, which SkyPilot
recommends for production: it alone offers graceful upgrades, server-side
authentication with roles, and an external database. SkyPilot's VM deployment
"does not have any authentication by default" and "does not offer graceful
upgrade"
([deploy](https://docs.skypilot.co/en/latest/reference/api-server/api-server-admin-deploy.html),
[upgrade](https://docs.skypilot.co/en/latest/reference/api-server/api-server-upgrade.html)).

| Part | Choice | $/month |
|---|---|---|
| EKS control plane | Standard support, $0.10/h | 73 |
| Node | 1 × m7i.2xlarge (8 vCPU, 32 GiB, $0.4032/h) | 294 |
| Database | RDS PostgreSQL db.t4g.micro, Multi-AZ, 20 GB, 7-day backups | 28 |
| Load balancer | Application Load Balancer, with TLS | 22 |
| NAT gateway | One, for the private node | 35 |
| Other | Node disk, Route 53 zone, domain | 6 |
| **Total** | | **about 460** |

**One node.** When it fails, EKS replaces it in about 10 minutes; running jobs
continue, and nothing is lost, because state is in RDS. Open-source SkyPilot
doesn't support more than one server replica
([upgrade](https://docs.skypilot.co/en/latest/reference/api-server/api-server-upgrade.html)),
so a second node ($294 a month, deferred) only shortens the reschedule, to
about a minute. The pod gets SkyPilot's minimum of 4 CPU and 8 GiB, which
serves 8 long requests at once and 16 launching and 400 running managed jobs;
a search is one managed job however many evaluations it runs.

**Authentication and TLS.** The chart's ingress-nginx is off
(`ingress-nginx.enabled=false`), since Kubernetes archived it on 2026-03-24, in
favour of the AWS Load Balancer Controller's ALB with an ACM certificate for a
name such as `skypilot.<domain>`. The server does basic auth itself
(`apiService.enableUserManagement=true`), with SkyPilot's two roles: `admin`
(the owner) and `user`. Agents get a service-account token with role `user`:
they can launch and read, but not change settings or the admin policy. A
`user` can also cancel any job; the agents' rules forbid it, and the archive
keeps the evidence.

**Database and server config.** The job table, users, and tokens are in RDS,
with 7 days of point-in-time restore, set through
`apiService.dbConnectionSecretName`. With an external database, SkyPilot
requires `apiService.config` to be null and has the server's config set in its
dashboard, and it ignores `apiService.config` on `helm upgrade` anyway
([upgrade](https://docs.skypilot.co/en/latest/reference/api-server/api-server-upgrade.html)).
So the server config is a committed file, `compute/server/config.yaml`, that
the owner pastes into the dashboard once ([setup](#setup-for-the-owner), step
6). It sets:

- `admin_policy: compute_jobs_admin_policy.Policy`, installed before the
  server starts by the chart's `apiService.preDeployHook`, as a `pip install`
  of `compute/server/admin_policy` at the release tag
  ([deploy](https://docs.skypilot.co/en/latest/reference/api-server/api-server-admin-deploy.html));
- `jobs.bucket: s3://<bucket>/uploads/`: managed jobs' uploaded working trees
  otherwise live on the pod's ephemeral disk and are lost when the pod is
  replaced
  ([upgrade](https://docs.skypilot.co/en/latest/reference/api-server/api-server-upgrade.html));
  this is stated for rolling updates, and that it also covers a node
  failure is unverified;
- `jobs.controller.task_logs_gc_retention_hours: 2160` (90 days);
- `allowed_clouds: [aws]`.

**Versions: one pin.** SkyPilot guarantees API compatibility between adjacent
minor versions from 0.10.0, and upgrades the server first
([upgrade](https://docs.skypilot.co/en/latest/reference/api-server/api-server-upgrade.html)).
The only SkyPilot version in this repository is the client's,
`skypilot==0.14.0` in `uv.lock`. `compute-server:provision` derives the
server's image tag and chart version from it, so each release tag names one
SkyPilot version for both, and a test fails if any other file names a SkyPilot
version. A project's pinned client then works with the server while their
minor versions are at most one apart; `compute-server:status` reports the
server's version (`sky api info`). The stable chart's name and its version
numbering are unverified: the docs' examples use `skypilot/skypilot-nightly
--devel` from `https://helm.skypilot.co`, and pin with `--version`.

**Failures.** With the server down, running jobs continue, nothing launches,
and preempted jobs wait. If RDS is lost, restore it; the archive holds every
result. A health check, and a watch that ends overdue machines, are
[deferred](#deferred).

**Upkeep**, from AWS's and SkyPilot's lifecycles (hours are estimates): the
node's AMI monthly; SkyPilot each minor release, server first; the agents'
token and the read-only S3 key quarterly; EKS one minor version yearly, since
after 14 months standard support ends and the control plane costs $0.60/h.
About two hours a month and half a day a year, through the
`compute-server-admin` skill.

## Job kinds

| Kind | What runs | Typical use | Nodes |
|---|---|---|---|
| `single` | One command on one machine | A simulation, a training run, an analysis | 1 |
| `multi-node` | The same command on every node, with `MASTER_ADDR`, `NODE_RANK`, `NNODES`, and `GPUS_PER_NODE` set for `torchrun` | Distributed training | 2 to the profile's maximum |
| `search` | One driver that dispatches many short evaluations to every GPU of every node, through `compute_jobs.fanout` | Evolutionary search, sweeps of short simulations | 1 to the profile's maximum |

Each kind is one managed job, so observe, the archive, the limits, and
recovery are the same for all three. Ten independent runs, such as seeds of a
training run, are ten `single` jobs.

### How a search fans out

Compared at 10,000 evaluations per generation:

| | Ray inside one managed job | SkyPilot pools | One managed job per evaluation |
|---|---|---|---|
| How | SkyPilot's `start_cluster` starts a user Ray cluster on port 6379 on every node (SkyPilot's own Ray uses 6380); the driver on rank 0 submits Ray tasks | Each evaluation is a managed job on a free pool worker | Each evaluation provisions a machine |
| Overhead per evaluation | Milliseconds | One managed job's scheduling | Minutes |
| Concurrency | Every GPU slot; Ray accepts fractional GPUs | One job per worker | 16 launching jobs at once |
| At 10,000 per generation | 16 L40S, 4 per GPU, 10 s each: about 26 minutes | 10,000 managed jobs per generation; beta | Not feasible |
| Recovery | A preempted node restarts the whole job | Per evaluation | Per evaluation |

**Decided: Ray inside one managed job.** Its overhead is small next to a
short evaluation, and the search stays one job to observe. The node count is
fixed for the job's life and one preempted node restarts every node, so
`fanout` checkpoints the population and random state each generation, and
every kind defaults to on-demand machines. Users don't write Ray code:

```python
from compute_jobs import fanout, progress

for generation in fanout.resume_generations(total=50):
    candidates = optimizer.ask()
    fitness = fanout.map(evaluate, candidates, gpus_per_evaluation=0.25)
    optimizer.tell(candidates, fitness)
    progress.report(
        step=generation, step_name="generation", best=max(fitness), best_name="fitness"
    )
    fanout.checkpoint(generation, optimizer)
```

`fanout.map` connects with `ray.init(address="localhost:6379")`, never
`"auto"`, turns off forwarding of workers' output to the driver, and counts
completed and failed evaluations in `progress.json`. With
`COMPUTE_JOB_SMOKE=1` it runs serially on the local machine, as `job:dry-run`
uses it.

**Spot.** `use_spot: true` is accepted for any kind; the dry run warns when
the job writes no checkpoints, since a preemption then restarts it from the
start, and for multi-node and search jobs, from any one node's preemption.

## Hardware profiles

Users name a profile; the admin policy turns it into an ordered list of
instance types, tried in turn. Profiles are in `limits.yaml`, which only the
admin changes: families, GPUs per node, maximum nodes, maximum run time, and
`enabled`.

| Profile | GPU, family | Fits | Per node, list price | Max nodes | Max $/h per job |
|---|---|---|---|---|---|
| `cpu` | none; c7i, m7i | CPU simulations, analysis, small drivers | up to m7i.4xlarge, 16 vCPU, $0.81/h | 4 | 3.23 |
| `gpu-small` | 1 × L4 (g6), then 1 × T4 (g4dn) | Development, small simulations, inference | g6.xlarge $0.80/h | 1 | 0.80 |
| `gpu-sim` | L40S (g6e): 1, 4, or 8 per node | Rendering simulators (Isaac Sim, RTX), GPU physics, search | g6e.48xlarge, 8 GPUs, $30.13/h | 2 | 60.26 |
| `gpu-train` | 8 × L40S (g6e.48xlarge), then 8 × A10G (g5.48xlarge, $16.29/h) | Training that fits in 44 GB per GPU | $30.13/h | 2 | 60.26 |

The P family (`gpu-train-large`: H100, A100) is [deferred](#deferred).
Isaac Sim doesn't support GPUs without RT cores, such as A100 and H100, and
names g6e for AWS, so anything that renders goes on the G family. Unsure, and
checked when a project first needs it: whether T4's 16 GB suffices for a
scene, and whether a simulator needs a newer driver than SkyPilot's AWS image
has (the wrapper's check catches it; only a custom machine image fixes it).

**Spending ceiling.** Decision D8 caps agent compute at $10,000 a day,
$416.67 an hour. EC2's vCPU quotas cap what can run at once; filling each
with the dearest allowed machine per vCPU (g6e.xlarge, $0.465 per vCPU-hour):

| Quota | Requested | Worst $/h |
|---|---|---|
| G and VT, on demand | 384 vCPUs | 178.66 |
| G and VT, spot | 384 vCPUs | 178.66 |
| Standard (c7i, m7i, about $0.05 per vCPU-hour) | 64 vCPUs | 3.23 |
| P, on demand | 0 | 0 |
| **Total** | | **360.55, or $8,653 a day** |

384 G vCPUs is two g6e.48xlarge on demand plus two on spot, which is why
`gpu-sim` and `gpu-train` allow 2 nodes. `compute-server:status` computes this
sum from the live quotas and `limits.yaml`, and fails above $416.67/h. The
admin policy enforces the per-job limits; the daily budget action is the
backstop, since AWS budget data lags by up to a day.

## The job image

Every job runs in this repository's image,
`ghcr.io/arjunbhargava/foundation-compute/compute-job:<release tag>`, built
from `Dockerfile` when a release is tagged: an `nvidia/cuda` runtime on Ubuntu
24.04, pinned by digest, with uv and the wrapper installed at that tag. The
client launches the image whose tag is its own version. The job's setup runs
`uv sync --locked` from the job's commit (1 to 3 minutes per attempt), so the
job has exactly the packages the agent tested with.

The admin policy accepts only this repository's images, by digest, with a
GitHub build-provenance attestation (`actions/attest-build-provenance`) from a
`v*` tag. Agents' VMs are x86_64 Ubuntu 24.04 with no GPU and no Docker, so
profiles list only x86 families, and the image workflow runs the wrapper and a
`uv sync --locked` of an example project inside the new image on a CPU runner.
A project needing CUDA wheels declares conflicting `cpu` and `cuda` extras; the
agent syncs `cpu`, the job `cuda`. Before the command, the wrapper fails the job
if the driver supports an older CUDA than the image, naming both. A project's
own image is [deferred](#deferred).

## Progress

A job reports progress by writing `progress.json` through
`compute_jobs.progress.report(...)`. The wrapper uploads it to the archive at
most every 30 seconds and at the end, and prints it to the log, at most every
60 seconds, as one line starting `COMPUTE_PROGRESS`.

```json
{
  "schema": 1,
  "phase": "evaluating",
  "step": 12,
  "step_name": "generation",
  "steps_total": 50,
  "done": 6400,
  "total": 10000,
  "failed": 3,
  "best": {"name": "fitness", "value": 0.873, "higher_is_better": true},
  "message": "",
  "updated_at": "2026-10-15T03:26:00Z"
}
```

Every field except `schema` and `updated_at` is optional. Observe shows the
latest progress, then a 20-line log tail, so an agent never reads a whole
log. It reads `progress.json` from the archive, or, without the read-only S3
key, the last `COMPUTE_PROGRESS` line through the server. Rank 0 writes
progress. Observe finds rank 0's machine from the job's log while the server
is up, and from `index/<job name>/` when it isn't. A job could write a false
marker under another job's name, since the job role can't be scoped to one
name; observe then shows both machines.

## How a job runs

1. An agent commits a job file and pushes, then runs `job:dry-run` and
   `job:launch`. The client checks its configuration, names and labels the
   job, and submits it with SkyPilot's SDK, uploading the working tree at the
   pushed commit; it refuses uncommitted or unpushed changes.
2. The admin policy turns kind and profile into resources, checks every
   limit, accepts only an allowed image, and forces
   `aws.remote_identity: compute-jobs-job`; otherwise SkyPilot's default,
   `LOCAL_CREDENTIALS`, copies the server's launch credentials onto the job's
   machines. It wraps the command in `timeout`, mounts
   `s3://<bucket>/checkpoints/<job name>/` at `$COMPUTE_JOB_CHECKPOINT_DIR`,
   and rejects a config that tries to change any of this.
3. On each machine, `python -m compute_jobs.run`, from the image, checks the
   driver and writes the run record. For `single` and `multi-node` it runs
   the command on every node. For `search` it starts Ray on every node, runs
   the command on rank 0 only, and keeps the others as Ray workers until rank
   0 exits. It writes progress, result, output, and log to the archive, and an
   empty marker, `index/<job name>/<machine id>`.
4. The server relaunches a preempted job, which resumes from its checkpoint,
   and deletes the machines when the job ends.
5. Any agent runs `job:observe`.

## Interface: contract v0

This section is the template plan's "Interface" and "Progress" sections at
`0a2f134`, unchanged. Changing a command, variable, exit code, or file format
needs the owner's agreement, through the template's orchestrator, in both
repositories.

### Commands and exit codes

The template's `mise run job:<command> -- <args>` runs
`compute-jobs <command> <args>`; the two forms take the same arguments and
exit with the same codes.

| Command | Does | Exit codes |
|---|---|---|
| `compute-jobs dry-run <job file>` | Validates, prices, and runs a CPU smoke test locally unless `smoke: false`; needs no server | 0 ready, 1 invalid or the smoke test failed |
| `compute-jobs launch <job file>` | Launches the pushed commit and prints the job name | 0 launched, 1 rejected, 2 not configured |
| `compute-jobs observe [<job name>] [--pr N] [--lines N] [--json]` | Shows state, recoveries, progress, machine, cost so far, run record, and log tail; with no name, lists jobs | 0 read, 1 no such job, 2 not configured |
| `compute-jobs cancel <job name>` | Cancels a job the caller launched | 0, 1, 2 as above |

Exit 2 means only "not configured". An argument error exits 1, not
`argparse`'s default of 2, so the template's wrapper can pass codes through.

### Variables

| Variable | Required | Meaning |
|---|---|---|
| `SKYPILOT_API_SERVER_ENDPOINT` | for launch, observe, cancel | The server's https:// URL |
| `SKYPILOT_SERVICE_ACCOUNT_TOKEN` | for launch, observe, cancel | The agents' token, role `user` |
| `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY` | no | The read-only key of the IAM user `compute-jobs-observer`, for progress and output from the archive |
| `COMPUTE_JOBS_BUCKET`, `COMPUTE_JOBS_AWS_REGION` | with the key | The archive's bucket and region |

The first two are SkyPilot's own names, so the pinned SkyPilot client reads
them directly. With either unset, or an endpoint that isn't `https://` or
points at this machine, launch, observe, and cancel exit 2 before any SkyPilot
call, because SkyPilot's client with no endpoint starts a local API server:

```text
SKYPILOT_API_SERVER_ENDPOINT is not set, so no job can be launched or
observed. This project is a client of a shared SkyPilot API server: ask the
owner to add SKYPILOT_API_SERVER_ENDPOINT and SKYPILOT_SERVICE_ACCOUNT_TOKEN
as Cursor secrets. The server is run with the compute-server-admin skill;
an agent never starts one. Nothing was started.
```

`dry-run` needs neither, and never calls SkyPilot: it checks the file with the
admin policy's own code and the release's `limits.yaml`, then runs the command
locally with `COMPUTE_JOB_SMOKE=1` and `CUDA_VISIBLE_DEVICES=""`. A command
that can't run without a GPU sets `smoke: false`; the dry run then skips the
smoke test, says so, and exits 0 for a valid file. The server's policy is
authoritative, so a dry run can pass and a launch be rejected (exit 1) when
the server's limits are newer than the client's release.

### Job file

```yaml
kind: search              # single, multi-node, or search
profile: gpu-sim          # a profile in limits.yaml
nodes: 2                  # multi-node and search only
command: python -m myproject.search
max_runtime_minutes: 180  # 1 to the profile's maximum
budget_usd: 200           # > 0; the task's compute budget bounds it
use_spot: false           # default
image: default            # or project (deferred)
uv_extras: [cuda]
smoke: true               # false if the command can't run without a GPU
seed: 1234                # recorded, and passed as COMPUTE_JOB_SEED
settings:                 # free-form; recorded, and passed as JSON
  population: 10000
```

The job name is `pr<PR number>-<file name>-<first 8 hex digits of the file's
SHA-256>`.

### Archive layout

In the bucket, each machine writes only under `machines/<machine id>/`, where
the machine id is its role session's `aws:userid`: the run record,
`progress.json`, result, output, and log. Each machine also writes an empty
marker, `index/<job name>/<machine id>`. Checkpoints are under
`checkpoints/<job name>/`, mounted at `$COMPUTE_JOB_CHECKPOINT_DIR` on every
attempt. `progress.json` is as in [Progress](#progress).

### What the template assumes

| Assumption | Status here |
|---|---|
| (a) An executable `compute-jobs <dry-run\|launch\|observe\|cancel> [args]`, installed by a pin in `mise.toml` | Confirmed; the pin's form is below |
| (b) The template's wrapper exits 2 itself, without calling the client, when the executable is missing, when launch, observe, or cancel lack the two server variables, or when the endpoint isn't https:// or points at this machine; otherwise it passes arguments and exit code through; dry-run needs no server variables | Confirmed. The client repeats the same checks, with the same message and exit 2, for anyone who runs it directly; and it exits 2 for nothing else |
| (c) The package provides `compute_jobs.progress.report(...)` and `compute_jobs.fanout` | Confirmed, with a difference: they are in the library distribution `compute-jobs`, which job code imports from the project's own environment, so a project whose jobs use them also adds that library, at the same tag, to its `pyproject.toml` (below) |
| (d) `observe --pr <n>` and `--json` work | Confirmed. `--pr <n>` lists jobs whose name starts `pr<n>-`. v0 doesn't define `--json`'s output; PR 5 fixes it as one object with a `schema` field, an addition to v0 |

### Installing a release

A release is a git tag, `v<major>.<minor>.<patch>`, with a GitHub release. A
project pins it in `mise.toml` with mise's `pipx:` backend (another name for
its `pypi:` backend), which installs with `uv tool install`
([mise](https://mise.jdx.dev/dev-tools/backends/pypi.html)):

```toml
"pipx:git+https://github.com/arjunbhargava/foundation-compute.git" = { version = "v0.1.0", uvx_args = "--python 3.13" }
```

- mise accepts a tag as a git source's version, and passes `uvx_args` to
  `uv tool install` ([mise](https://mise.jdx.dev/dev-tools/backends/pypi.html)).
  This exact line is from the documentation only; AC 17 checks it in PR 8.
- `--python 3.13` is needed: SkyPilot 0.14.0 supports Python up to 3.13, and
  `uv tool install` ignores a `.python-version` file and `requires-python`
  ([uv](https://docs.astral.sh/uv/concepts/tools/)), while the template pins
  3.14. mise passes `--python` itself only when it manages Python, which the
  template doesn't. That uv then downloads 3.13 on a machine without it is
  unverified until PR 8.
- Git sources install without mise's dependency lock, so SkyPilot's own
  dependencies resolve at install time
  ([mise](https://mise.jdx.dev/dev-tools/backends/pypi.html)); this
  repository's `uv.lock` doesn't constrain them.
- Job code that imports `compute_jobs` adds the library to the project's own
  environment, with
  `uv add "compute-jobs @ git+https://github.com/arjunbhargava/foundation-compute.git@v0.1.0#subdirectory=lib"`
  (unverified until PR 8). It can't come from the mise pin: that is a tool
  environment on Python 3.13, and the job's code runs in the project's
  environment, on the project's Python, where Ray must be importable too.
- Dependabot can't track the mise pin: mise isn't among its ecosystems
  ([GitHub](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories)),
  and the template's `mise.toml` says the same. Whether its `uv` ecosystem
  bumps a git dependency's tag is unverified. Until either is shown, the
  template's orchestrator bumps both pins by hand from the release notes.

## Packages and files

One tag releases everything, so the client, the wrapper in the image, the
admin policy on the server, and the SkyPilot version always match.

| Distribution | Import package | Python | Contents | Installed by |
|---|---|---|---|---|
| `foundation-compute`, at the root | `compute_jobs_cli` | 3.13 | The `compute-jobs` executable: configuration checks, dry-run, launch, observe, cancel; depends on `skypilot==0.14.0`, boto3, and the two below | A project's mise pin |
| `compute-jobs`, in `lib/` | `compute_jobs` | 3.12 and later (unverified for Ray on 3.14) | `job_file`, `progress`, `run` (the wrapper), `run_record`, `archive`, and `fanout`, with Ray as the `fanout` extra | The image; a project's `pyproject.toml` |
| `compute-jobs-admin-policy`, in `compute/server/admin_policy/` | `compute_jobs_admin_policy` | 3.13 | The admin policy and `limits.yaml` | The server's `preDeployHook`; the CLI, for dry-run |

The placeholder package `src/foundation_compute/` is removed in PR 1, and
`.python-version` and the root's `requires-python` move from 3.14 to 3.13.

Other files:

- `Dockerfile` and `.github/workflows/compute-image.yml`; `release.yml`.
- `compute/server/`: `values.yaml` (no versions), `config.yaml`,
  `eksctl.yaml`, `aws/*.json` (IAM policies), and the provision and status
  scripts; `mise.admin.toml` at the root.
- `.github/workflows/ci.yml`: the three distributions' lint and tests.
- `.github/dependabot.yml`: `docker` for `Dockerfile`, and `uv` for `lib/`
  and `compute/server/admin_policy/`.
- `.github/CODEOWNERS`: `compute/server/`.
- `.cursor/skills/compute-server-admin/SKILL.md`, a draft for the owner to
  edit (finding F2).
- `docs/api/python.md`, `docs/architecture.md`, `AGENTS.md`, and this page,
  rewritten as built.

## Admin tasks

- The admin tasks are `MISE_ENV=admin mise run
  compute-server:<provision|status>`, in `mise.admin.toml` with their tools
  (AWS CLI, eksctl, kubectl, Helm). mise loads it only with `MISE_ENV=admin`,
  so `mise run check`, CI, and agents neither list nor install them.
- Each needs the AWS CLI profile named by
  `COMPUTE_SERVER_ADMIN_AWS_PROFILE`, an IAM Identity Center login on the
  owner's machine, never a Cursor secret, and asks for the cluster name to be
  typed before changing anything.
- `provision` is idempotent: rerun at a new tag, it applies that tag's policy,
  limits, and SkyPilot version with `helm upgrade --install`.
- `status` changes nothing. It checks that a request without a token gets
  401, that the `agents` token can't change settings, that the policy rejects
  an over-limit job, that the budget action exists, the server's version, and
  the quota ceiling.
- Only a person runs them. The template's `compute-cost` rule update says so
  for agents.

## Credentials

| Name | Where | Secret? | Read by |
|---|---|---|---|
| `SKYPILOT_API_SERVER_ENDPOINT`, `SKYPILOT_SERVICE_ACCOUNT_TOKEN` | Cursor secrets | token: yes | the client |
| `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`, `COMPUTE_JOBS_BUCKET`, `COMPUTE_JOBS_AWS_REGION` | Cursor secrets | key: yes | observe |
| `COMPUTE_SERVER_ADMIN_AWS_PROFILE` | the owner's shell | no | admin tasks |
| The RDS connection string | a Kubernetes secret, `skypilot-db-connection-uri` | yes | the server |

The server's AWS identity is the role `compute-jobs-launcher`, given to its
pod through IAM Roles for Service Accounts, so no long-lived launch key
exists. Whether SkyPilot 0.14.0 accepts that identity is unverified; the
fallback is a key in the Kubernetes secret the chart reads, rotated every 90
days. Job machines run as `compute-jobs-job`, which can read the bucket, write
only `machines/${aws:userid}/*`, `index/*`, and `checkpoints/*`, and stop or
terminate only its own instance. So one job can't alter another's archive,
but could overwrite another's checkpoints, which costs at most a restart. The
read-only key exposes job logs and outputs, nothing more.

## Setup for the owner

None of these steps is confirmed done. Each works in a phone browser except 5
and 9, which run on a laptop. Steps 1 to 4 can start now; the rest wait for
PR 10.

1. Create an AWS account, `agent-jobs`, under the negotiated agreement, and
   sign in to it with IAM Identity Center:
   <https://console.aws.amazon.com/organizations/v2/home/accounts>.
2. In `us-east-1`, request vCPU quotas: "Running On-Demand G and VT
   instances" 384 and "All G and VT Spot Instance Requests" 384. Check that
   "Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances" is 64,
   and leave "Running On-Demand P instances" at 0:
   <https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas>.
3. Pick the server's host name, such as `skypilot.<domain>`, and create a
   Route 53 hosted zone for the domain, registering one (about $15 a year) if
   you have none: <https://console.aws.amazon.com/route53/v2/hostedzones>.
4. Add GitHub as an identity provider, for the deferred watch workflow:
   OpenID Connect, URL `https://token.actions.githubusercontent.com`,
   audience `sts.amazonaws.com`:
   <https://console.aws.amazon.com/iam/home#/identity_providers/create>.
5. On a laptop logged in to `agent-jobs`, set
   `COMPUTE_SERVER_ADMIN_AWS_PROFILE` and run
   `MISE_ENV=admin mise run compute-server:provision`. It creates the EKS
   cluster, RDS, the ACM certificate, the S3 bucket (private, 90-day
   expiry), the roles `compute-jobs-launcher` and `compute-jobs-job`, the
   policy `compute-jobs-deny-launch`, the IAM user `compute-jobs-observer`
   and its key, and the server. It prints the endpoint, the dashboard URL,
   and the observer key once.
6. In the dashboard, change the initial admin password, and paste
   `compute/server/config.yaml` into the config page. Create a service
   account `agents`, role `user`, 90-day expiry, and note the expiry date.
7. Add the Cursor secrets `SKYPILOT_API_SERVER_ENDPOINT`,
   `SKYPILOT_SERVICE_ACCOUNT_TOKEN` (the `agents` token),
   `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`,
   `COMPUTE_JOBS_BUCKET`, and `COMPUTE_JOBS_AWS_REGION`:
   <https://cursor.com/dashboard>, Cloud Agents > Secrets.
8. Create a daily cost budget, `compute-jobs-daily`, of $10,000, with email
   alerts at 50% and 80%, and an action at 100% of actual cost that applies
   `compute-jobs-deny-launch` to `compute-jobs-launcher`:
   <https://console.aws.amazon.com/costmanagement/home#/budgets/create>.
   Alerts alone don't stop spend; the action and the quotas do.
9. Run `MISE_ENV=admin mise run compute-server:status`; it must pass.
10. If Cursor's agent network allowlist is on, add the server's host name and
    `<bucket>.s3.us-east-1.amazonaws.com`.
11. Approve the spike's compute budget in its PR (below).

## Cost

Nothing has been launched, and no AWS resource exists. Estimates use AWS
on-demand list prices in `us-east-1`; the negotiated rates are lower, by an
unknown amount, so each is a ceiling.

- **Method**, for a job: nodes × the profile's dearest instance per hour ×
  `max_runtime_minutes` / 60. The dry run prints this; the admin policy
  rejects a job whose ceiling exceeds `budget_usd`.
- **Server**: about $460 a month, $15 a day, from provisioning (step 5) on,
  whether or not jobs run.
- **Spike**: about $10 (below).
- **Worst case**: the quotas cap it at $360.55 an hour, under D8's $416.67.

## Pull requests

Stacked from `main`, in this order; each is useful when it merges and within
500 lines. Design, admin policy, and provisioning PRs run on Opus; the rest
on Sonnet. A PR marked "yes" gets `needs-human-review`. "AC" refers to the
[acceptance criteria](#acceptance-criteria).

| # | PR | Model | Review | Done when |
|---|---|---|---|---|
| 1 | Package layout: the three distributions as a uv workspace, Python 3.13 for the CLI, the placeholder package removed, the API pages | Opus | yes: package split and Python pin | `mise run check` and `mise run docs` pass; AC 14 |
| 2 | `compute-jobs` with its four commands and configuration checks | Sonnet | | AC 1; AC 2 for argument errors, extended by PRs 4 and 5 |
| 3 | The job file and job name, and the admin policy with `limits.yaml` (`cpu`, `gpu-small`, `gpu-sim`, `gpu-train`) and the quota ceiling check | Opus | yes: limits bound spend | AC 5, 6, 13 |
| 4 | `dry-run` and `launch`, with a fake SkyPilot SDK | Sonnet | | AC 7; launch submits the expected task and refuses unpushed changes |
| 5 | `progress`, `observe` (with `--json` fixed), and `cancel` | Sonnet | | AC 10 |
| 6 | The wrapper, run record, and archive, with S3 faked by moto | Sonnet | | AC 9, 11 |
| 7 | The image and `compute-image.yml`, with attestation and the in-image smoke test | Sonnet | yes: a workflow that publishes | AC 16 |
| 8 | Releases: `release.yml`, a ruleset protecting `v*` tags, release notes naming the contract and SkyPilot versions; tag `v0.1.0` | Sonnet | yes: release policy | AC 17; the template can pin `v0.1.0` |
| 9 | IAM policy files, `mise.admin.toml`, `compute-server:status` | Opus | yes: IAM | AC 3, 12 |
| 10 | Provisioning: `eksctl.yaml`, `values.yaml`, `config.yaml`, `compute-server:provision` for one node | Opus | yes: provisioning | AC 4; `helm template` renders offline; provision refuses without the profile or the typed name |
| 11 | The `compute-server-admin` skill, drafted for the owner | Sonnet | yes: people write skills (F2) | The owner has edited it |
| 12 | The spike: `fanout`, `examples/toy_search/`, the real run, and this page and `docs/architecture.md` rewritten as built | Opus | yes: compute spend | AC 8, 15 |

**What CI can test**: everything in AC 1 to 14 and 16 to 17, with no AWS
account, network, or server, using a fake SkyPilot SDK, moto for S3, a fake
`nvidia-smi`, and Ray on one CI machine; IAM policies only statically (the
allowed prefixes and actions in the JSON). **What it can't**: provisioning
(EKS, RDS, ALB, IRSA), whether IAM policies behave as written, SkyPilot's
behaviour behind its SDK (admin policy hooks, spot recovery, consolidation
mode), GPU drivers, Ray across real nodes, and cost. Those are checked by
`compute-server:status` and the spike (AC 15).

## The spike

**Not approved.** No AWS action and no compute spend happen until the owner
approves the budget in PR 12, per the `compute-cost` rule; until a
`compute-jobs` skill exists in this repository, that rule requires asking for
every job.

A toy evolutionary search, `examples/toy_search/`, with a CPU stand-in for a
simulation (a noisy analytic fitness function with a sleep, so evaluations
take seconds), run end to end through the real server:

- kind `search`, profile `cpu`, 2 nodes (m7i.4xlarge), 5 generations of 200
  evaluations, `gpus_per_evaluation=0`, so Ray schedules each evaluation on
  its default of one CPU
  ([Ray](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html));
- `max_runtime_minutes: 60`, `budget_usd: 2`: a ceiling of
  2 × $0.81/h × 1 h = $1.62 per attempt;
- with about five attempts, including failed ones, under about $10 in all.

It passes when the search finishes 5 generations, the command ran on rank 0
only and both nodes evaluated, a second agent sees progress with
`job:observe` while it runs, and a cancel then relaunch resumes from the last
checkpoint. Not counted: the server's standing $15 a day.

## Acceptance criteria

Each is a named test needing no AWS account, network, or server, except 15.

1. With either server variable unset, or the endpoint not `https://` or
   local, `compute-jobs launch|observe|cancel` exit 2 with the v0 message, and
   a fake SDK records no call; `dry-run` makes no SkyPilot call.
2. Each exit code in the commands table comes from a test, and an argument
   error exits 1.
3. The default mise configuration lists no `compute-server:` task, and those
   tasks exit with a message when `COMPUTE_SERVER_ADMIN_AWS_PROFILE` is unset.
4. `uv.lock` holds the only SkyPilot version in the repository, and
   provisioning derives the server's image and chart from it.
5. The job file accepts each kind with its fields, and rejects a missing or
   unknown kind or profile, `nodes` on a `single` job, and `nodes` above the
   profile's maximum.
6. The admin policy maps each profile to its ordered instance types; rejects
   a disabled profile, a job over any limit, a missing or exceeded
   `budget_usd`, an image not allowed or not by digest, and a config setting
   `remote_identity` or `admin_policy`; and rewrites each accepted job with
   `remote_identity: compute-jobs-job`, the `timeout`, and the checkpoint
   mount.
7. `dry-run` prints the maximum cost and runs the smoke test with no GPU
   visible; with `smoke: false` it skips it and exits 0 for a valid file; it
   warns on spot without checkpoints.
8. In a 2-node search the command runs once, on rank 0, and the other node
   receives evaluations; `fanout.map` keeps the candidates' order, counts
   failures, and runs serially with `COMPUTE_JOB_SMOKE=1`;
   `resume_generations` resumes after the last checkpoint.
9. `progress.report` writes a valid `progress.json`; the wrapper uploads it at
   most every 30 s; observe shows it from the archive, through `index/` when
   the server is down, and without the S3 key from the last
   `COMPUTE_PROGRESS` line.
10. Observe prints state, recoveries, progress, machine, cost so far, log
    tail, and run record for each kind, from a fake SDK; `--json` and `--pr`
    work.
11. The wrapper writes a complete run record and final state for exit 0, a
    nonzero exit, and the `timeout`, and fails before the command when a fake
    `nvidia-smi` reports an older CUDA than the image's.
12. The job role allows writes only under `machines/${aws:userid}/`,
    `index/`, and `checkpoints/`.
13. The quota ceiling check fails above $416.67 an hour.
14. `mise run check` passes with no AWS or server credentials.
15. On the real server: a request without a token gets 401, the `agents`
    token can't change settings, and the spike passes.
16. The image's smoke test passes inside the built image, and the policy
    rejects an image without a release-tag attestation.
17. On a clean VM with only Python 3.14, the mise pin above gives a working
    `compute-jobs dry-run`, and the library installs into a 3.14 project.

## Deferred

The base above is enough to run a real search through the real server and to
learn what this plan got wrong. Each item keeps its design from the
[template's plan](https://github.com/arjunbhargava/foundation/blob/0a2f134ea7d5ccaf8d6bfe5f598dcc273f2049e2/docs/compute-jobs.md);
the PR that builds it moves it out of this table.

| Item | Until then | Freed when |
|---|---|---|
| The 15-minute watch workflow: terminating machines past their deadline, or all once the budget action fires; cancelling the jobs of closed, unmerged PRs; an authoritative `index/` from EC2 tags | The in-job `timeout`, SkyPilot's teardown, the quotas, and the budget action, which blocks launches but stops no machine; the owner can terminate machines in the EC2 console | Jobs run with no person watching, a machine outlives its job, or a job runs over a day |
| The `compute-job:` check run, and the Cursor Automation that starts a follow-up agent from it | Agents poll `job:observe` | A job outlasts the agent that launched it and someone must act on its result |
| Copier's `compute` question (the template's), and `compute_server_admin` | Projects pin the client by hand; one repository, this one, runs the server | The first project made from the template needs compute jobs |
| Project images: `compute/image.yaml`, vendor bases such as Isaac Sim's, other repositories in the image allowlist | Every job runs this repository's image | A project needs a system package, CUDA version, or simulator the image lacks |
| `gpu-train-large` (P family: H100, A100) and fan-out beyond 2 nodes or 16 L40S | `gpu-sim` and `gpu-train`, at most 2 nodes | A project needs H100 or A100, or more than 16 L40S at once; both need new quotas and a rechecked ceiling |
| A second server node, a Route 53 health check, token rotation, and upgrade and restore procedures | One node; the owner notices an outage when a command fails; tokens rotated by hand; 7 days of RDS backups and the archive | Downtime matters; jobs run unattended; the first token is 2 weeks from expiry; the first SkyPilot upgrade |

## Open decisions

1. **The library's second pin.** Job code needs `compute-jobs` in the
   project's `pyproject.toml` as well as the CLI in `mise.toml`, both at the
   same tag. The alternative, the wrapper putting the image's copy on the
   job's `PYTHONPATH`, breaks when the project's Python differs from the
   image's and leaves Ray out of the project's environment. Needs the
   template's orchestrator.
2. **`observe --json`'s shape**, fixed in PR 5; the template's skill may parse
   it, so its orchestrator reviews PR 5.
3. **Server config in the dashboard**, since Helm can't set it with RDS: is a
   scripted way to apply and read `config.yaml` available, so `status` can
   compare it? Unverified; otherwise `status` checks behaviour (the policy
   rejects an over-limit job).
4. **The chart's persistent volume**: keep it for logs (on EKS it needs the
   EBS CSI driver add-on
   ([deploy](https://docs.skypilot.co/en/latest/reference/api-server/api-server-admin-deploy.html))
   and a node group in the volume's zone), or turn it off with
   `storage.enabled=false` and rely on RDS, `jobs.bucket`, and the archive.
   Which state, if any, lives only on it is unverified.
5. **Standard quota.** The server's node uses 8 of the 64 Standard vCPUs, so
   a 4-node `cpu` job (64 vCPUs) can't start. Raise the quota to 96 (adds
   about $1.60/h to the ceiling), or cap `cpu` at 3 nodes.
6. **IRSA**, if SkyPilot rejects it: accept the rotated key in a Kubernetes
   secret, or wait for support.
7. **Tag immutability**: a ruleset blocking updates and deletion of `v*` tags
   (PR 8), or pins by commit, which mise also accepts but reads worse.
8. **Offline chart checks in CI**: a job with `MISE_ENV=admin` and no
   credentials that runs `helm template` would test PR 10 in CI, but puts the
   admin tools in CI, which the plan avoided.

## Decisions made

By the owner, 2026-10-15: SkyPilot on AWS, on the negotiated-rate account; a
shared server on EKS and RDS through Helm, with projects as clients only by
default; one server node; the S3 archive, with a read-only key for agents;
hardware profiles; the three job kinds, with search as Ray inside one managed
job; on-demand by default, spot opt-in; one SkyPilot pin, the client's; and
the base first, with everything under [Deferred](#deferred) left for later.
