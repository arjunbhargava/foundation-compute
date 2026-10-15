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
| `the job server at https://... didn't answer within 10 s` | The server is down or unreachable; nothing was launched or cancelled | Ask the owner to run `compute-server:status`; observe still reads the archive with the read-only key |
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
- **Hardware profile**: a named, ordered list of instance-type entries in
  `limits.yaml`, such as `gpu-sim`, that a job names instead of a machine.
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
| `multi-node` | The same command on every node, with the distributed variables below set | Distributed training | 1 to the profile's maximum |
| `search` | One driver that dispatches many short evaluations to every GPU of every node, through `compute_jobs.fanout` | Evolutionary search, sweeps of short simulations | 1 to the profile's maximum |

Each kind is one managed job, so observe, the archive, the limits, and
recovery are the same for all three. Ten independent runs, such as seeds of a
training run, are ten `single` jobs.

### Distributed training on 1 or N nodes

A `multi-node` job accepts `nodes: 1`, so one training script runs unchanged
on one node or many. The kind keeps its name, because renaming it would
change contract v0. Before the command, the wrapper exports these on every
node, from SkyPilot's own variables
([SkyPilot](https://docs.skypilot.co/en/latest/running-jobs/distributed-jobs.html)):

| Variable | Value | From |
|---|---|---|
| `NNODES` | Number of nodes; 1 on one node | `SKYPILOT_NUM_NODES` |
| `NODE_RANK` | This node's rank, 0 to `NNODES`−1; 0 on one node | `SKYPILOT_NODE_RANK` |
| `MASTER_ADDR` | Rank 0's IP address; this node's own on one node | First line of `SKYPILOT_NODE_IPS` |
| `MASTER_PORT` | 29500, fixed | The wrapper |
| `GPUS_PER_NODE` | GPUs on each node; 0 on a CPU profile | `SKYPILOT_NUM_GPUS_PER_NODE` |

The job's command passes them to `torchrun`, which then sets `RANK`,
`LOCAL_RANK`, `WORLD_SIZE`, and `LOCAL_WORLD_SIZE` in each process
([PyTorch](https://docs.pytorch.org/docs/2.14/elastic/run.html)):

```bash
torchrun --nnodes=$NNODES --node_rank=$NODE_RANK --nproc_per_node=$GPUS_PER_NODE \
  --master_addr=$MASTER_ADDR --master_port=$MASTER_PORT train.py
```

On a CPU profile the command passes `--nproc_per_node=1`, as
`examples/multi_node/` does. `progress.report` writes only from global rank 0
(`RANK`, or `NODE_RANK` when `RANK` is unset), so N processes give one
progress file.

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

optimizer = fanout.restore(initial=Optimizer(seed=1234))
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
uses it. `fanout.restore` returns the state the last checkpoint saved, or its
`initial` argument when there is none.

**Spot.** `use_spot: true` is accepted for any kind; the dry run warns when
the job writes no checkpoints, since a preemption then restarts it from the
start, and for multi-node and search jobs, from any one node's preemption.

## Hardware profiles

A job names a profile; the admin policy turns it into the profile's enabled
entries, tried in order. Profiles live in `limits.yaml` as data, so any GPU
instance type that EC2 offers is added by editing the list, not the code; the
admin policy and the ceiling check read whatever the list says. Only the
admin changes it, and a change ships in a release (`provision` applies it).

```yaml
schema_version: 1
daily_cap_usd: 10000          # decision D8; never raised without the owner
quotas:                       # vCPUs requested in us-east-1
  standard_on_demand: 64
  g_vt_on_demand: 384
  g_vt_spot: 384
  p_on_demand: 0
  p_spot: 0
profiles:
  gpu-train-large:
    max_runtime_minutes: 1440
    entries:                  # tried in order
      - instance_type: p5.48xlarge
        quota: p_on_demand
        spot_quota: null      # the spot quota group; null unless spot_allowed
        accelerator: H100
        gpus_per_node: 8
        gpu_memory_gb: 80
        vcpus: 192
        usd_per_hour: 55.04
        max_nodes: 2
        spot_allowed: false
        enabled: false        # until the P quota is raised
```

For a job, the policy keeps the entries that are enabled, allow its node
count, and allow spot if it asks for spot. It rejects the job if none is
left, and prices it at the dearest one kept. `compute-server:status` checks
each entry against EC2's own description of the instance type (vCPUs, GPU
count and memory), and fails if an entry's price is below AWS's current list
price, so a ceiling never understates.

The release ships these, with x86 families only, since the image is x86:

| Profile | Entries, in order | Fits | Max nodes | Enabled |
|---|---|---|---|---|
| `cpu` | m7i.4xlarge (16 vCPU, $0.81/h) | CPU simulations, analysis, small drivers, the examples | 3 | yes |
| `gpu-small` | g6.xlarge (1 × L4, 24 GB, $0.80/h); g6e.xlarge (1 × L40S, 48 GB, $1.861/h); g4dn.xlarge (1 × T4, 16 GB, $0.526/h) | Development, small simulations, inference | 1 | yes |
| `gpu-sim` | g6e.48xlarge (8 × L40S, $30.13/h); g6e.12xlarge (4 × L40S, $10.49/h) | Rendering simulators (Isaac Sim, RTX), GPU physics, search | 2 | yes |
| `gpu-train` | g6e.48xlarge | Training that fits in 44 GB per GPU | 2 | yes |
| `gpu-sim-large` | g6e.48xlarge, on demand only | Searches over more than 16 L40S | 4 | no, until the G quotas change |
| `gpu-train-large` | p5.48xlarge (8 × H100, 80 GB, 192 vCPU, $55.04/h); p4d.24xlarge (8 × A100, 40 GB, 96 vCPU, $21.96/h); both on demand only | Large-model training | 2 | no, until the P quota is raised |

Prices here are rounded; `limits.yaml` has AWS's exact list prices, and its
comments say where they came from. Every profile allows 1440 minutes, and
`cpu` has no spot, since no Standard spot quota is requested for the ceiling
to count. `cpu` allows 3 nodes, not 4, because the server's node takes 8
of the 64 Standard vCPUs. A 24 GB training profile (8 × A10G, g5.48xlarge) can
be added as data if a project wants one.

Isaac Sim doesn't support GPUs without RT cores, such as A100 and H100, and
names g6e for AWS, so anything that renders uses the G family. Unsure, and
checked when a project first needs it: whether T4's 16 GB suffices for a
scene, and whether a simulator needs a newer driver than SkyPilot's AWS image
has (the wrapper's check catches it; only a custom machine image fixes it).

**Spending ceiling.** EC2's vCPU quotas cap what can run at once, per quota
group. `compute-server:status` fills each group with its dearest enabled
entry per vCPU and fails if the sum exceeds `daily_cap_usd` / 24, which is
$416.67 an hour under D8. Per vCPU-hour, the dearest G entry is g6e.xlarge
($0.465), the dearest P entry p5.48xlarge ($0.287), and Standard is about
$0.05. As shipped:

| Quota | Requested | Worst $/h |
|---|---|---|
| G and VT, on demand | 384 vCPUs | 178.66 |
| G and VT, spot | 384 vCPUs | 178.66 |
| Standard | 64 vCPUs | 3.23 |
| P, on demand and spot | 0 | 0 |
| **Total** | | **360.55, or $8,653 a day: under D8's cap** |

Enabling the large entries, against the same cap:

| Change | Quotas: G on demand / G spot / P on demand | Worst $/h | Against $416.67/h |
|---|---|---|---|
| `gpu-train-large`, 1 node | 384 / 384 / 192 | 415.59 | Under, by $1.08 |
| `gpu-train-large`, 2 nodes | 384 / 384 / 384 | 470.63 | **Over** |
| The same, with less G spot | 384 / 256 / 384 | 411.07 | Under |
| `gpu-sim-large`, 4 nodes | 768 / 0 / 0 | 360.54 | Under, with no G spot |
| 8 × p5.48xlarge (64 H100) | 0 / 0 / 1,536 | 443.55 | **Over, even with no G quota** |

So the base and modest large runs fit under D8 by trading quotas between
groups; anything like the last row needs a higher daily cap, which only the
owner can set ([open decisions](#open-decisions)). Every job is still
bounded by its own `budget_usd`, and the daily budget action is the
backstop, since AWS budget data lags by up to a day.

## The job image

Every job runs in this repository's image, held in a private Amazon ECR
repository, `compute-jobs/job`, in the `agent-jobs` account, with immutable
tags and one tag per release. It is built from `Dockerfile`: an
`nvidia/cuda` runtime on Ubuntu 24.04, pinned by digest, with uv and the
wrapper installed at that tag. SkyPilot needs a Debian-based image whose user
is root or has passwordless sudo, and it installs itself inside the container
at launch
([SkyPilot](https://docs.skypilot.co/en/latest/examples/docker-containers.html)).
The job's setup runs `uv sync --locked` from the job's commit (1 to 3 minutes
per attempt), so the job has exactly the packages the agent tested with.

- **Push.** `.github/workflows/compute-image.yml` builds the image and runs
  its smoke test (below) on every PR. On a `v*` tag it attests the image with
  `actions/attest-build-provenance`, and pushes it through the role
  `compute-jobs-image-push`, assumed with GitHub's OIDC token. The role
  trusts only `repo:arjunbhargava/foundation-compute:environment:release`,
  the claim GitHub sends for a job in that environment
  ([GitHub](https://docs.github.com/en/actions/reference/security/oidc)), and
  the environment allows only `v*` tags. Until the owner has provisioned, the
  push step is skipped.
- **Pull.** Job machines pull with their own role, `compute-jobs-job`, which
  may read only that repository: SkyPilot uses the instance's IAM role for
  ECR when the job sets `SKYPILOT_DOCKER_USERNAME` and
  `SKYPILOT_DOCKER_PASSWORD` to empty strings and `SKYPILOT_DOCKER_SERVER` to
  the registry
  ([SkyPilot](https://docs.skypilot.co/en/latest/examples/docker-containers.html)),
  which the admin policy sets.
- **Accept.** For `image: default`, the client asks for the image tagged with
  its own version; the policy resolves the tag to its digest in ECR and
  launches the digest. It rejects any image outside
  `<account>.dkr.ecr.us-east-1.amazonaws.com/compute-jobs/job`, any reference
  not by digest, and any digest without a release-tag attestation, which it
  checks through GitHub's attestations API and caches per digest
  (unverified that the API serves this without a token).

Agents' VMs are x86_64 Ubuntu 24.04 with no GPU and no Docker, so the image
workflow runs the wrapper and the examples' `uv sync --locked` inside the new
image on a CPU runner. A project needing CUDA wheels declares conflicting
`cpu` and `cuda` extras; the agent syncs `cpu`, the job `cuda`. Before the
command, the wrapper fails the job if the driver supports an older CUDA than
the image, naming both. Project images, in further repositories in the same
registry, are [deferred](#deferred).

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

Every field except `schema` and `updated_at` is optional; the proposed v0.1
adds `schema_version` ([below](#proposed-v01-versioned-formats)). Observe shows the
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
   driver and writes the run record. For `single` it runs the command; for
   `multi-node` it exports the distributed variables and runs the command on
   every node. For `search` it starts Ray on every node, runs
   the command on rank 0 only, and keeps the others as Ray workers until rank
   0 exits. It writes progress, result, output, and log to the archive, and an
   empty marker, `index/<job name>/<machine id>`.
4. The server relaunches a preempted job, which resumes from its checkpoint,
   and deletes the machines when the job ends.
5. Any agent runs `job:observe`.

## Interface: contract v0

This section is the template plan's "Interface" and "Progress" sections at
`0a2f134`, unchanged, followed by the proposed v0.1 additions, which are
pending agreement with the template. Changing a command, variable, exit code, or file format
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
The proposed v0.1 names each failure on stderr's first line
([Failure kinds](#proposed-v01-failure-kinds)).

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

### Proposed v0.1: versioned formats

**Pending agreement with the template.** These additions add or rename no
command, variable, or exit code, and a v0 reader keeps working:

1. **Job file:** an optional integer `schema_version`; a file without it
   means 1.
2. **`progress.json`:** an integer `schema_version`, written alongside v0's
   `schema` with the same value. Readers use `schema_version`, and fall back
   to `schema` when it is absent.
3. **Run record:** `machines/<machine id>/run_record.json`, with a required
   `schema_version`. v0 names the run record but not its format.
4. **Archive layout:** a marker object, `archive.json` at the bucket's root,
   `{"schema_version": 1}`, written by `provision`.
5. **`multi-node` accepts `nodes: 1`**, and the wrapper also exports
   `MASTER_PORT`, as in
   [Distributed training](#distributed-training-on-1-or-n-nodes).
6. **`observe --json`** prints one object with a `schema_version` and a
   `kind` (addition 10).
7. **`$COMPUTE_JOB_OUTPUT_DIR`**, set by the wrapper: files the job writes
   there are uploaded to `machines/<machine id>/output/`. v0 names the
   archive's output but not how a job writes it.
8. **JSON Schema files**, one per format, in
   `lib/src/compute_jobs/schemas/` (`job-file`, `progress`, `run-record`,
   `archive`, and `observe` for `observe --json`, each
   `.v<major>.schema.json`), published at each release tag and tested
   against valid and invalid fixtures.
9. **An unreachable server**: `observe` exits 1 when the server doesn't
   answer within 10 seconds and the read-only key isn't set, widening v0's
   "no such job" to "couldn't read the job"; with the key it exits 0 from the
   archive. `launch` and `cancel` exit 1, with v0's "rejected" widened the
   same way ([Running an example end to end](#running-an-example-end-to-end)).
10. **Failure kinds**: every exit 1 and 2 prints `kind=<kind>` as the first
    line of stderr, and `observe --json` carries the same `kind`
    ([below](#proposed-v01-failure-kinds)).

The versioning policy, for every format:

- An added optional field doesn't change the version.
- A breaking change (a removed, renamed, retyped, or newly required field, or
  a changed meaning) increments the integer major.
- Readers accept the current and the previous major: `observe`, the wrapper,
  `dry-run`, the admin policy, and the template's `compute-jobs` skill.
- A reader that refuses a version names the major it saw and the majors it
  accepts, such as `progress.json has schema_version 3; this observe reads 1
  and 2; upgrade the client`. The exit codes stay as in v0: `dry-run` and
  `launch` exit 1 for a job file they refuse, and `observe` exits 0, printing
  the refusal in place of the progress it can't read.

### Proposed v0.1: failure kinds

**Pending agreement with the template**, as addition 10. Every exit 1 or 2
from `compute-jobs` writes, as the first line of stderr, exactly
`kind=<kind>` and a newline: no spaces, no other text, and `<kind>` matches
`[a-z][a-z0-9_]*`. The human message follows on the next lines, unchanged,
and stdout is unaffected. Exit 0 writes no `kind=` line. The template's skill
and wrapper branch on that first line, never on the message:

```text
$ compute-jobs observe pr81-search-00000000
kind=unknown_job
No job named pr81-search-00000000. List this PR's jobs with:
  compute-jobs observe --pr 81
```

`observe --json` prints its object on stdout whatever the exit code, with a
`kind` beside `schema_version`: `null` on exit 0, and otherwise the kind on
the stderr line, with a `message`. Any `--json` output a later release adds
to another command does the same. For exit 2 the line comes before v0's
message, and the template's wrapper, which exits 2 itself before calling the
client, prints the same line: a change on the template's side.

| Kind | Exit | Commands | Meaning | v0 meaning it refines |
|---|---|---|---|---|
| `not_configured` | 2 | launch, observe, cancel | A server variable is unset, or the endpoint isn't `https://` or points at this machine | "not configured" |
| `argument_error` | 1 | all | An unknown command or option, or a missing or malformed argument | An argument error |
| `invalid_job_file` | 1 | dry-run, launch | The file isn't a valid job file: a YAML error, a missing, unknown, or mistyped field, an unknown kind or profile, or `nodes` on a `single` job | dry-run's "invalid"; launch's "rejected" |
| `refused_job_file` | 1 | dry-run, launch | A valid job file this release refuses: an unsupported `schema_version`, or a limit in the release's `limits.yaml` (nodes, run time, budget, image, or no enabled entry left) | dry-run's "invalid"; launch's "rejected" |
| `smoke_failed` | 1 | dry-run | The smoke test exited nonzero or ran out of time | "the smoke test failed" |
| `rejected` | 1 | launch, cancel | The server or its admin policy refused the request, such as a limit newer than the client's release, or cancelling a job the caller didn't launch | "rejected" |
| `unknown_job` | 1 | observe, cancel | No job has that name | "no such job" |
| `server_unreachable` | 1 | launch, observe, cancel | The server didn't answer in time (addition 9); for observe, only without the read-only key | "rejected"; "no such job" |
| `branch_not_ready` | 1 | launch | Uncommitted or unpushed changes, or no open PR for the branch to name the job by | "rejected" |
| `unauthorized` | 1 | launch, observe, cancel | The server refused the token | "rejected"; "no such job" |
| `internal_error` | 1 | all | An unexpected error in the client; the traceback follows the message | none: Python's own exit 1 |

All eight requested kinds fit v0's table. `invalid_job_file` and
`refused_job_file` split dry-run's "invalid" and the client-side part of
launch's "rejected"; `rejected` keeps the server-side part. The last three
kinds are proposed here because without them some exit-1 paths would have no
kind.

The kinds are part of the contract and are versioned with `observe --json`
under the policy above. Adding a kind is additive and changes no version.
Renaming or removing one, or changing its meaning or exit code, is breaking:
it increments that format's major and needs the template's agreement. A
reader that meets a kind it doesn't know treats it as a failure with that
exit code. The client defines the kinds once, in `compute_jobs_cli.kinds`.
The `observe` JSON Schema types `kind` by the pattern above rather than as a
list, so a validating reader accepts a newly added kind.

### What the template assumes

| Assumption | Status here |
|---|---|
| (a) An executable `compute-jobs <dry-run\|launch\|observe\|cancel> [args]`, installed by a pin in `mise.toml` | Confirmed; the pin's form is below |
| (b) The template's wrapper exits 2 itself, without calling the client, when the executable is missing, when launch, observe, or cancel lack the two server variables, or when the endpoint isn't https:// or points at this machine; otherwise it passes arguments and exit code through; dry-run needs no server variables | Confirmed. The client repeats the same checks, with the same message and exit 2, for anyone who runs it directly; and it exits 2 for nothing else. Under v0.1's failure kinds, the wrapper passes stderr through unchanged, so `kind=` stays the first line |
| (c) The package provides `compute_jobs.progress.report(...)` and `compute_jobs.fanout` | Confirmed, with a difference: they are in the library distribution `compute-jobs`, which job code imports from the project's own environment, so a project whose jobs use them also adds that library, at the same tag, to its `pyproject.toml` (below) |
| (d) `observe --pr <n>` and `--json` work | Confirmed. `--pr <n>` lists jobs whose name starts `pr<n>-`. v0 doesn't define `--json`'s output; PR 6 fixes it as one object with a `schema_version` field, an addition to v0 |

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
  This exact line is from the documentation only; AC 21 checks it in PR 11.
- `--python 3.13` is needed: SkyPilot 0.14.0 supports Python up to 3.13, and
  `uv tool install` ignores a `.python-version` file and `requires-python`
  ([uv](https://docs.astral.sh/uv/concepts/tools/)), while the template pins
  3.14. mise passes `--python` itself only when it manages Python, which the
  template doesn't. That uv then downloads 3.13 on a machine without it is
  unverified until PR 11.
- Git sources install without mise's dependency lock, so SkyPilot's own
  dependencies resolve at install time
  ([mise](https://mise.jdx.dev/dev-tools/backends/pypi.html)); this
  repository's `uv.lock` doesn't constrain them.
- Job code that imports `compute_jobs` adds the library to the project's own
  environment, with
  `uv add "compute-jobs @ git+https://github.com/arjunbhargava/foundation-compute.git@v0.1.0#subdirectory=lib"`
  (unverified until PR 11). It can't come from the mise pin: that is a tool
  environment on Python 3.13, and the job's code runs in the project's
  environment, on the project's Python, where Ray must be importable too.
- Dependabot can't track the mise pin: mise isn't among its ecosystems
  ([GitHub](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories)),
  and the template's `mise.toml` says the same. Whether its `uv` ecosystem
  bumps a git dependency's tag is unverified. Until either is shown, the
  template's orchestrator bumps both pins by hand from the release notes.

## Packages and files

One tag releases everything, so the client, the wrapper in the image, the
admin policy on the server, the schemas, and the SkyPilot version always
match.

| Distribution | Import package | Python | Contents | Installed by |
|---|---|---|---|---|
| `foundation-compute`, at the root | `compute_jobs_cli` | 3.13 | The `compute-jobs` executable: configuration checks, dry-run, launch, observe, cancel; depends on `skypilot==0.14.0`, boto3, and the two below | A project's mise pin |
| `compute-jobs`, in `lib/` | `compute_jobs` | 3.12 and later; `fanout`'s tests pass with Ray 2.59.0 on 3.14, whose PyPI release has 3.14 wheels, though Ray's installation page lists only up to 3.13 | `job_file`, `progress`, `run` (the wrapper), `run_record`, `archive`, `fanout` (Ray as its extra), and `schemas/`; depends on jsonschema and PyYAML (both MIT) | The image; a project's `pyproject.toml` |
| `compute-jobs-admin-policy`, in `compute/server/admin_policy/` | `compute_jobs_admin_policy` | 3.13 | The admin policy and `limits.yaml` | The server's `preDeployHook`; the CLI, for dry-run |

The placeholder package `src/foundation_compute/` is removed in PR 1, and
`.python-version` and the root's `requires-python` move from 3.14 to 3.13.

Other files:

- `lib/src/compute_jobs/schemas/*.schema.json`, with fixtures in
  `lib/tests/fixtures/`.
- `examples/single/`, `examples/multi_node/`, `examples/fanout/`: each a job
  file, a README, and its code ([below](#reference-runs)).
- `Dockerfile`, `.github/workflows/compute-image.yml`, and `release.yml`.
- `compute/server/`: `values.yaml` (no versions), `config.yaml`,
  `eksctl.yaml`, the provision and status scripts, and `aws/`, the IAM
  policies: `launcher.json`, `job.json`, `observer.json`,
  `deny-launch.json`, and `image-push.json` with its trust policy;
  `mise.admin.toml` at the root.
- `.github/workflows/ci.yml`: the three distributions' lint and tests, and
  the examples' dry runs.
- `.github/dependabot.yml`: `docker` for `Dockerfile`, and `uv` for `lib/`,
  `compute/server/admin_policy/`, and the examples.
- `.github/CODEOWNERS`: `compute/server/`.
- `.cursor/skills/compute-server-admin/SKILL.md`, a draft for the owner to
  edit (finding F2).
- `docs/api/python.md`, `docs/architecture.md`, `AGENTS.md`, and this page,
  rewritten as built.

## Reference runs

Three small examples, built in the base, show users and agents how to
instrument a job end to end, and let the owner check that the system works.
Each has a job file on the `cpu` profile (its README says which profile to
use on GPUs), a short README, calls `progress.report`, writes a result to
`$COMPUTE_JOB_OUTPUT_DIR` and a checkpoint to `$COMPUTE_JOB_CHECKPOINT_DIR`,
and has a CI test that runs its `dry-run`, smoke test included.

CI never needs the API server or any AWS call. Its test of each example is
the `dry-run` alone, which is local: the admin policy's code and
`limits.yaml` check the job file, and the CPU smoke test runs the example's
code, with no SkyPilot call and no server variables set. That tests each
example's job file and smoke test, and nothing beyond them.

| Example | Kind, nodes | What it does |
|---|---|---|
| `examples/single/` | `single`, 1 | Ten steps of a toy simulation; checkpoints each step and resumes from the last |
| `examples/multi_node/` | `multi-node`, 2; also runs with `nodes: 1` | `torchrun` with the gloo backend: each rank logs `rank R of W`, then an all-reduce of the ranks, checked against W(W−1)/2 |
| `examples/fanout/` | `search`, 2 | The toy evolutionary search: a CPU stand-in simulation (a noisy analytic fitness function with a sleep, so evaluations take seconds), 5 generations of 200 evaluations through `compute_jobs.fanout`, with `gpus_per_evaluation=0`, so Ray schedules each on its default of one CPU ([Ray](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html)) |

### Running an example end to end

Each example also runs on the real server, on request, whenever the server is
up. That run is manual, by an agent or the owner when asked, and never a CI
job; it costs money, so the `compute-cost` rule applies, as in
[the spike](#the-spike). PR 9
adds the four `job:*` mise tasks to this repository, running `uv run
compute-jobs`, so the sequence is the same here as in a project. From a
branch with an open PR, its changes committed and pushed, with the two server
variables set (and the read-only key, for the last step):

```sh
mise run job:dry-run -- examples/single/job.yaml
mise run job:launch -- examples/single/job.yaml   # prints the job name
mise run job:observe -- <job name>                # repeat until it ends
```

Observe prints the state, progress, log tail, and each machine's id. The
result lands at `s3://<bucket>/machines/<machine id>/output/result.json`, with
the run record, `progress.json`, and log beside it, and the checkpoint under
`s3://<bucket>/checkpoints/<job name>/`; `index/<job name>/` lists the job's
machines. `multi_node` and `fanout` use the same three commands with their
own `job.yaml`; for `multi_node` on 1 node, change only `nodes:` to 1, commit,
and push. What each run should show is in
[How the owner verifies](#how-the-owner-verifies).

When the server is down, nothing hangs and nothing is launched:

- With a server variable unset, `launch`, `observe`, and `cancel` exit 2
  with `kind=not_configured` and the v0 message above, before any network
  call.
- With the variables set but the server unreachable, the client checks the
  endpoint's health before any SkyPilot call, with a 10-second timeout
  (SkyPilot documents `GET <endpoint>/api/health`; unverified for 0.14.0).
  `launch` and `cancel` then exit 1 with `kind=server_unreachable`, saying the server at that endpoint
  didn't answer, that nothing was launched or cancelled, and to ask the owner
  to run `compute-server:status`. Every later request to the server has a
  60-second timeout, so a server that fails mid-command also ends in exit 1.
- `observe` then reads the archive, if the read-only key is set: it exits 0,
  says the server is unreachable, and shows progress and the machines from
  `index/<job name>/`. Without the key it exits 1 with the same message.
- `dry-run` needs no server, so it works as usual.

These add no exit code; they are v0.1 additions 9 and 10, pending agreement
with the template ([Proposed v0.1](#proposed-v01-versioned-formats)).

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
  limits, and SkyPilot version with `helm upgrade --install`. It also creates
  the ECR repository `compute-jobs/job` (immutable tags, a lifecycle rule
  keeping the last 10 release images), the role `compute-jobs-image-push`,
  and the archive's `archive.json` marker.
- `status` changes nothing. It checks that a request without a token gets
  401, that the `agents` token can't change settings, that the policy rejects
  an over-limit job, that the budget action exists, the server's version,
  `limits.yaml`'s entries, and the quota ceiling.
- Only a person runs them. The template's `compute-cost` rule update says so
  for agents.

## Credentials

| Name | Where | Secret? | Read by |
|---|---|---|---|
| `SKYPILOT_API_SERVER_ENDPOINT`, `SKYPILOT_SERVICE_ACCOUNT_TOKEN` | Cursor secrets | token: yes | the client |
| `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`, `COMPUTE_JOBS_BUCKET`, `COMPUTE_JOBS_AWS_REGION` | Cursor secrets | key: yes | observe |
| `COMPUTE_JOBS_ECR_PUSH_ROLE_ARN`, `COMPUTE_JOBS_AWS_REGION` | variables of the GitHub environment `release` | no | `compute-image.yml` |
| `COMPUTE_SERVER_ADMIN_AWS_PROFILE` | the owner's shell | no | admin tasks |
| The RDS connection string | a Kubernetes secret, `skypilot-db-connection-uri` | yes | the server |

The server's AWS identity is the role `compute-jobs-launcher`, given to its
pod through IAM Roles for Service Accounts, so no long-lived launch key
exists; it may also look up digests in the ECR repository. Whether SkyPilot
0.14.0 accepts that identity is unverified; the fallback is a key in the
Kubernetes secret the chart reads, rotated every 90 days. Job machines run as
`compute-jobs-job`, which can read the bucket and pull from the ECR
repository, write only `machines/${aws:userid}/*`, `index/*`, and
`checkpoints/*`, and stop or terminate only its own instance. So one job
can't alter another's archive, but could overwrite another's checkpoints,
which costs at most a restart. The read-only key exposes job logs and
outputs, nothing more. The image push role exists only for the release
environment's workflow, and can push only to `compute-jobs/job`.

## Setup for the owner

None of these steps is confirmed done. Each works in a phone browser except 5
and 10, which run on a laptop. Steps 1 to 4 can start now; the rest wait for
PR 13.

1. Create an AWS account, `agent-jobs`, under the negotiated agreement, and
   sign in to it with IAM Identity Center:
   <https://console.aws.amazon.com/organizations/v2/home/accounts>.
2. In `us-east-1`, request vCPU quotas: "Running On-Demand G and VT
   instances" 384, "All G and VT Spot Instance Requests" 384, and "Running
   On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances" 64. Leave
   "Running On-Demand P instances" at 0. A new account starts at 0 for G and
   P and 5 for Standard
   ([AWS](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)):
   <https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas>.
3. Pick the server's host name, such as `skypilot.<domain>`, and create a
   Route 53 hosted zone for the domain, registering one (about $15 a year) if
   you have none: <https://console.aws.amazon.com/route53/v2/hostedzones>.
4. Add GitHub as an identity provider, for the image push (and later the
   watch workflow): OpenID Connect, URL
   `https://token.actions.githubusercontent.com`, audience
   `sts.amazonaws.com`:
   <https://console.aws.amazon.com/iam/home#/identity_providers/create>.
5. On a laptop logged in to `agent-jobs`, set
   `COMPUTE_SERVER_ADMIN_AWS_PROFILE` and run
   `MISE_ENV=admin mise run compute-server:provision`. It creates the EKS
   cluster, RDS, the ACM certificate, the S3 bucket (private, 90-day
   expiry), the ECR repository, the roles `compute-jobs-launcher`,
   `compute-jobs-job`, and `compute-jobs-image-push`, the policy
   `compute-jobs-deny-launch`, the IAM user `compute-jobs-observer` and its
   key, and the server. It prints the endpoint, the dashboard URL, the push
   role's ARN, and the observer key once.
6. In the dashboard, change the initial admin password, and paste
   `compute/server/config.yaml` into the config page. Create a service
   account `agents`, role `user`, 90-day expiry, and note the expiry date.
7. Add the Cursor secrets `SKYPILOT_API_SERVER_ENDPOINT`,
   `SKYPILOT_SERVICE_ACCOUNT_TOKEN` (the `agents` token),
   `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`,
   `COMPUTE_JOBS_BUCKET`, and `COMPUTE_JOBS_AWS_REGION`:
   <https://cursor.com/dashboard>, Cloud Agents > Secrets.
8. Create the GitHub environment `release`, limited to tags matching `v*`,
   with the variables `COMPUTE_JOBS_ECR_PUSH_ROLE_ARN` (from step 5) and
   `COMPUTE_JOBS_AWS_REGION` (`us-east-1`):
   <https://github.com/arjunbhargava/foundation-compute/settings/environments/new>.
   Then rerun the image workflow for the latest tag, from the Actions tab.
9. Create a daily cost budget, `compute-jobs-daily`, of $10,000, with email
   alerts at 50% and 80%, and an action at 100% of actual cost that applies
   `compute-jobs-deny-launch` to `compute-jobs-launcher`:
   <https://console.aws.amazon.com/costmanagement/home#/budgets/create>.
   Alerts alone don't stop spend; the action and the quotas do.
10. Run `MISE_ENV=admin mise run compute-server:status`; it must pass.
11. If Cursor's agent network allowlist is on, add the server's host name and
    `<bucket>.s3.us-east-1.amazonaws.com`.
12. Approve the spike's budget in PR 15, then follow
    [How the owner verifies](#how-the-owner-verifies).

Optional, later, only when a project needs a disabled profile. Each changes
the ceiling, so enable the entries in `limits.yaml`, rerun step 10, and if it
fails, see the cap under [open decisions](#open-decisions):

13. For `gpu-sim-large` (4 × g6e.48xlarge): "Running On-Demand G and VT
    instances" 768, and "All G and VT Spot Instance Requests" 0:
    <https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas>.
14. For `gpu-train-large`: "Running On-Demand P instances", 192 per
    p5.48xlarge node (96 per p4d.24xlarge): same link. A person at AWS
    reviews accelerator quota requests, and not instantly (a community
    article on
    [AWS Builder Center](https://builder.aws.com/content/3JsNTHZYZ3ZNq7V6Eq8ontfZVMF/gpus-on-aws-above-the-cluster));
    that P requests are often declined for a new account is unverified, so
    ask well before a project depends on it. Capacity is separate from
    quota: on-demand P capacity is often unavailable even with quota.
15. For a `cpu` profile with more nodes: "Running On-Demand Standard ..."
    96 lets `cpu` allow 4 nodes beside the server's: same link.

## Cost

Nothing has been launched, and no AWS resource exists. Estimates use AWS
on-demand list prices in `us-east-1`; the negotiated rates are lower, by an
unknown amount, so each is a ceiling.

- **Method**, for a job: nodes × the dearest entry kept per hour ×
  `max_runtime_minutes` / 60. The dry run prints this, and the admin policy
  rejects a job whose ceiling exceeds `budget_usd`. Provisioning, the image
  pull, and setup add up to about 10 minutes per node per attempt
  (unverified), which the ceiling doesn't count. Linux instances are billed
  per second
  ([AWS](https://aws.amazon.com/ec2/pricing/on-demand/)), so a short run
  costs less than its ceiling.
- **Server**: about $460 a month, $15 a day, from provisioning (step 5) on,
  whether or not jobs run.
- **ECR**: $0.10 per GB-month of storage, and pulls within the region are
  free ([AWS](https://aws.amazon.com/ecr/pricing/)). At an unverified 5 to
  10 GB per image and 10 images kept, at most about $10 a month.
- **Spike**: about $3.50 a full pass, under the $10 target
  ([below](#the-spike)).
- **Worst case**: the quotas cap it at $360.55 an hour as shipped, under
  D8's $416.67 ([spending ceiling](#hardware-profiles)).

## Pull requests

Stacked from `main`, in this order; each is useful when it merges and within
500 lines, and a PR that grows past it splits in two. Design, data formats,
admin policy, and provisioning run on Opus; the rest on Sonnet. A PR marked
"yes" gets `needs-human-review`. "AC" refers to the
[acceptance criteria](#acceptance-criteria).

| # | PR | Model | Review | Done when |
|---|---|---|---|---|
| 1 | Package layout: the three distributions as a uv workspace, Python 3.13 for the CLI, the placeholder package removed, the API pages | Opus | yes: package split and Python pin | `mise run check` and `mise run docs` pass; AC 17 |
| 2 | `compute-jobs` with its four commands, configuration checks, and the failure kinds with their top-level handler | Sonnet | yes: failure kinds, v0.1 pending the template | AC 1; AC 2 for argument errors; AC 23 for `not_configured`, `argument_error`, and `internal_error` |
| 3 | Versioned schemas: the five JSON Schema files, fixtures, and the readers' version check | Opus | yes: formats, v0.1 pending the template | AC 13 |
| 4 | The job file and job name, the admin policy, `limits.yaml` as the compute list, and the ceiling check | Opus | yes: limits bound spend | AC 5, 6, 14 |
| 5 | `dry-run` and `launch`, with a fake SkyPilot SDK | Sonnet | | AC 2, 7, and 22 and 23 for their kinds; launch submits the expected task and refuses unpushed changes |
| 6 | `progress`, `observe` (with `--json` fixed), and `cancel` | Sonnet | | AC 2, 10, and 22 and 23 for their kinds |
| 7 | The wrapper, run record, archive, and distributed variables, with S3 faked by moto | Sonnet | | AC 9, 11, 12 |
| 8 | `fanout` | Opus | | AC 8 |
| 9 | The three examples, their local CI dry runs, the `job:*` mise tasks, and each README's end-to-end sequence | Sonnet | | AC 16 |
| 10 | The image and `compute-image.yml`: build and smoke test on PRs, attest and push to ECR on tags | Sonnet | yes: publishes through a cloud role | AC 18 |
| 11 | Releases: `release.yml`, a ruleset protecting `v*` tags, release notes naming the contract, schema, and SkyPilot versions; tag `v0.1.0` | Sonnet | yes: release policy | AC 21; the template can pin `v0.1.0` |
| 12 | IAM policy files, `mise.admin.toml`, `compute-server:status` | Opus | yes: IAM | AC 3, 15 |
| 13 | Provisioning: `eksctl.yaml`, `values.yaml`, `config.yaml`, the ECR repository, and `compute-server:provision` for one node | Opus | yes: provisioning | AC 4; `helm template` renders offline; provision refuses without the profile or the typed name |
| 14 | The `compute-server-admin` skill, drafted for the owner | Sonnet | yes: people write skills (F2) | The owner has edited it |
| 15 | The spike: the three examples through the real server, verified by the owner; this page and `docs/architecture.md` rewritten as built | Opus | yes: compute spend | AC 19, 20 |

**What CI can test**: AC 1 to 18 and 21 to 23, with no AWS account, network, or
server, using a fake SkyPilot SDK, a socket that never answers for AC 22, moto for S3, a fake `nvidia-smi`, Ray and
`torchrun` on one CI machine, and a container with only Python 3.14 for AC
21; IAM policies only statically (the allowed prefixes, actions, and trust
in the JSON); the image workflow's build and smoke test, but not its push.
**What it can't**: provisioning (EKS, RDS, ALB, IRSA, ECR), whether IAM
policies behave as written, SkyPilot's behaviour behind its SDK (admin
policy hooks, ECR pulls, spot recovery, consolidation mode), GPU drivers,
Ray and `torchrun` across real nodes, and cost. `compute-server:status` and
the spike check those (AC 19, 20). No CI job ever calls the server or AWS:
the examples' end-to-end runs are manual, on request
([Running an example end to end](#running-an-example-end-to-end)).

## The spike

**Not approved.** No AWS action and no compute spend happen until the owner
approves the budget in PR 15, per the `compute-cost` rule; until a
`compute-jobs` skill exists in this repository, that rule requires asking for
every job.

The spike runs the three [reference runs](#reference-runs) through the real
server, on the `cpu` profile (m7i.4xlarge, $0.81/h):

| Run | Nodes × `max_runtime_minutes` | Ceiling |
|---|---|---|
| `single` | 1 × 15 | $0.20 |
| `multi_node`, 2 nodes | 2 × 15 | $0.40 |
| `multi_node`, 1 node | 1 × 15 | $0.20 |
| `fanout` | 2 × 30 | $0.81 |
| `fanout`, cancelled after generation 2 and relaunched | 2 × 30 | $0.81 |
| Setup, about 10 minutes for each of 8 node launches (unverified) | | $1.08 |
| **A full pass** | | **$3.50** |

$10 covers a full pass, a rerun of every run, and a margin. If more attempts
than that are needed, the agent stops and asks in the PR before spending
more. Not counted: the server's standing $15 a day.

### How the owner verifies

1. In PR 15, the agent posts the table above. Reply `Approved: $10`, or a
   smaller figure.
2. For each run, the agent follows
   [Running an example end to end](#running-an-example-end-to-end) and posts
   one PR comment holding the outputs of `job:dry-run`, `job:launch`, and,
   once it ends, `job:observe <job name>`, and a listing of
   `s3://<bucket>/index/<job name>/` and of each
   `s3://<bucket>/machines/<machine id>/`.
3. `single` passes when observe says `SUCCEEDED (exit 0)` and `step 10 of
   10`, and its machine holds `run_record.json`, `progress.json`, the log,
   and `output/result.json`, with a checkpoint under
   `checkpoints/<job name>/`.
4. `multi_node`, 2 nodes, passes when observe says `SUCCEEDED`, the log tail
   shows `rank 0 of 2`, `rank 1 of 2`, and `all-reduce 1 (expected 1)`, and
   `index/<job name>/` lists two machines.
5. `multi_node`, 1 node (the same job file with only `nodes: 1` changed),
   passes when observe says `SUCCEEDED` and the log shows `rank 0 of 1` and
   `all-reduce 0 (expected 0)`.
6. `fanout` passes when observe says `SUCCEEDED`, `generation 5 of 5`, `200
   of 200 evaluations`, and `0 failed`, and best fitness never falls between
   the `COMPUTE_PROGRESS` lines it shows. A second agent's comment, posted
   while the run was going, shows its own `observe` output with progress.
7. The relaunched `fanout` passes when its log says `resuming after
   generation 2` and it ends `SUCCEEDED`.
8. The agent posts each run's final `cost so far` and their total; it passes
   under the approved figure.
9. Reply `Verified`, or name the step that failed.

## Acceptance criteria

Each is a named test needing no AWS account, network, or server, except 19
and 20.

1. With either server variable unset, or the endpoint not `https://` or
   local, `compute-jobs launch|observe|cancel` exit 2 with the v0 message, and
   a fake SDK records no call; `dry-run` makes no SkyPilot call.
2. Each exit code in the commands table comes from a test, and an argument
   error exits 1.
3. The default mise configuration lists no `compute-server:` task, and those
   tasks exit with a message when `COMPUTE_SERVER_ADMIN_AWS_PROFILE` is unset.
4. `uv.lock` holds the only SkyPilot version in the repository, and
   provisioning derives the server's image and chart from it.
5. The job file accepts each kind with its fields, `multi-node` and `search`
   with 1 to the profile's maximum nodes; rejects a missing or unknown kind
   or profile, `nodes` on a `single` job, and `nodes` above the maximum; and
   reads a file without `schema_version` as 1.
6. The admin policy keeps, in order, the enabled entries that allow the
   job's nodes and spot choice, rejects the job when none is left, and prices
   it at the dearest; rejects a job over any limit, a missing or exceeded
   `budget_usd`, an image outside the ECR repository, not by digest, or
   without a release-tag attestation, and a config setting
   `remote_identity` or `admin_policy`; and rewrites each accepted job with
   `remote_identity: compute-jobs-job`, the ECR credential variables, the
   `timeout`, and the checkpoint mount.
7. `dry-run` prints the maximum cost and runs the smoke test with no GPU
   visible; with `smoke: false` it skips it and exits 0 for a valid file; it
   warns on spot without checkpoints.
8. In a 2-node search (two Ray nodes on one machine) the command runs once,
   on rank 0, and the other node receives evaluations; `fanout.map` keeps the
   candidates' order, counts failures, and runs serially with
   `COMPUTE_JOB_SMOKE=1`; `resume_generations` resumes after the last
   checkpoint.
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
12. From fake SkyPilot variables for 1 and 2 nodes, the wrapper exports
    `NNODES`, `NODE_RANK`, `MASTER_ADDR`, `MASTER_PORT`, and
    `GPUS_PER_NODE`; `progress.report` writes only from global rank 0.
13. Each JSON Schema accepts its valid fixtures and rejects its invalid ones;
    each reader accepts the current and previous major and refuses the next,
    naming the major it saw; `progress.json` carries `schema` and
    `schema_version` with one value.
14. `limits.yaml`'s entries validate; the ceiling as shipped is $360.55 an
    hour; enabling `gpu-train-large` with `p_on_demand: 384` and the other
    quotas as shipped ($470.63 an hour) fails the check against
    `daily_cap_usd`, and passes with `g_vt_spot: 256` ($411.07).
15. The job role writes only under `machines/${aws:userid}/`, `index/`, and
    `checkpoints/`, and pulls only from `compute-jobs/job`; the push role
    trusts only the `release` environment and pushes only there.
16. Each example's `dry-run`, smoke test included, passes in CI, calls
    `progress.report`, and writes a result and a checkpoint; `multi_node`'s
    smoke test runs `torchrun` on one node.
17. `mise run check` passes with no AWS or server credentials.
18. The image's smoke test passes inside the built image, and the workflow
    pushes only from the `release` environment on a `v*` tag, skipping the
    push when the role variable is unset.
19. On the real server, `compute-server:status` passes: a request without a
    token gets 401, and the `agents` token can't change settings.
20. The spike passes every step of
    [How the owner verifies](#how-the-owner-verifies).
21. On a machine with only Python 3.14, the mise pin above gives a working
    `compute-jobs dry-run`, and the library installs into a 3.14 project.
22. With the endpoint `https://compute-jobs.test`, which passes AC 1's checks
    and which the test resolves to a socket that accepts connections and
    never answers, `launch` and `cancel` exit 1 within 15 seconds naming the
    endpoint, and a fake SDK records no submission; `observe` exits 0 from a
    moto archive with the read-only key set, and 1 without it; `dry-run` is
    unaffected.
23. One test for each kind in [Failure kinds](#proposed-v01-failure-kinds)
    triggers it through every command the table lists: `not_configured` by an
    unset variable, `argument_error` by an unknown option, `invalid_job_file`
    by an unknown field, `refused_job_file` by `schema_version: 99` and by
    nodes above the maximum, `smoke_failed` by a command that exits 3,
    `rejected` by a fake SDK's policy rejection and a cancel of another
    caller's job, `unknown_job` by an unused name, `server_unreachable` as in
    AC 22, `branch_not_ready` by an uncommitted change, `unauthorized` by a
    fake SDK's 401, and `internal_error` by a fake SDK raising an unexpected
    exception. Each checks the exit code, that stderr's first line is exactly
    `kind=<kind>`, and, for observe, that `--json` prints the same `kind`
    and validates against its schema. On exit 0, stderr has no `kind=` line
    and `--json` has `kind: null`. Another test fails when this table and
    `compute_jobs_cli.kinds` differ.

## Deferred

The base above is enough to run real jobs of every kind through the real
server and to learn what this plan got wrong. Each item keeps its design from
the
[template's plan](https://github.com/arjunbhargava/foundation/blob/0a2f134ea7d5ccaf8d6bfe5f598dcc273f2049e2/docs/compute-jobs.md);
the PR that builds it moves it out of this table.

| Item | Until then | Freed when |
|---|---|---|
| The 15-minute watch workflow: terminating machines past their deadline, or all once the budget action fires; cancelling the jobs of closed, unmerged PRs; an authoritative `index/` from EC2 tags | The in-job `timeout`, SkyPilot's teardown, the quotas, and the budget action, which blocks launches but stops no machine; the owner can terminate machines in the EC2 console | Jobs run with no person watching, a machine outlives its job, or a job runs over a day |
| The `compute-job:` check run, and the Cursor Automation that starts a follow-up agent from it | Agents poll `job:observe` | A job outlasts the agent that launched it and someone must act on its result |
| Copier's `compute` question (the template's), and `compute_server_admin` | Projects pin the client by hand; one repository, this one, runs the server | The first project made from the template needs compute jobs |
| Project images: `compute/image.yaml`, vendor bases such as Isaac Sim's, each in its own repository in the same ECR registry | Every job runs this repository's image | A project needs a system package, CUDA version, or simulator the image lacks |
| A second server node, a Route 53 health check, token rotation, and upgrade and restore procedures | One node; the owner notices an outage when a command fails; tokens rotated by hand; 7 days of RDS backups and the archive | Downtime matters; jobs run unattended; the first token is 2 weeks from expiry; the first SkyPilot upgrade |

## Open decisions

1. **The library's second pin.** Job code needs `compute-jobs` in the
   project's `pyproject.toml` as well as the CLI in `mise.toml`, both at the
   same tag. The alternative, the wrapper putting the image's copy on the
   job's `PYTHONPATH`, breaks when the project's Python differs from the
   image's and leaves Ray out of the project's environment. Needs the
   template's orchestrator.
2. **The v0.1 additions**
   ([Proposed v0.1](#proposed-v01-versioned-formats)) need the template's
   orchestrator, including its skill reading the current and previous major.
3. **A higher daily cap.** The shipped quotas fit under D8's $10,000 a day;
   `gpu-train-large` at 2 nodes fits only with less G spot quota, and
   training on 8 or more p5.48xlarge needs a cap above $10,000 a day
   ($443.55 an hour, $10,645 a day, for 8 with no G quota at all). Only the
   owner can raise it, in the template's D8; until then `status` fails such a
   change.
4. **Server config in the dashboard**, since Helm can't set it with RDS: is a
   scripted way to apply and read `config.yaml` available, so `status` can
   compare it? Unverified; otherwise `status` checks behaviour (the policy
   rejects an over-limit job).
5. **The chart's persistent volume**: keep it for logs (on EKS it needs the
   EBS CSI driver add-on
   ([deploy](https://docs.skypilot.co/en/latest/reference/api-server/api-server-admin-deploy.html))
   and a node group in the volume's zone), or turn it off with
   `storage.enabled=false` and rely on RDS, `jobs.bucket`, and the archive.
   Which state, if any, lives only on it is unverified.
6. **IRSA**, if SkyPilot rejects it: accept the rotated key in a Kubernetes
   secret, or wait for support.
7. **Tag immutability**: a ruleset blocking updates and deletion of `v*` tags
   (PR 11), or pins by commit, which mise also accepts but reads worse.
8. **The attestation check**: the policy asks GitHub's attestations API at
   launch, cached per digest, or the release workflow records each attested
   digest somewhere the policy reads without GitHub (such as an ECR tag
   only the push role can write).
9. **PyTorch in CI** for `examples/multi_node/`: the CPU wheel is a large
   download for every CI run; the alternative is a rendezvous over plain
   sockets that shows the same variables but not `torchrun`.
10. **Offline chart checks in CI**: a job with `MISE_ENV=admin` and no
    credentials that runs `helm template` would test PR 13 in CI, but puts the
    admin tools in CI, which the plan avoided.

## Decisions made

By the owner, 2026-10-15: SkyPilot on AWS, on the negotiated-rate account; a
shared server on EKS and RDS through Helm, with projects as clients only by
default; one server node; the S3 archive, with a read-only key for agents;
hardware profiles; the three job kinds, with search as Ray inside one managed
job; on-demand by default, spot opt-in; one SkyPilot pin, the client's; and
the base first, with everything under [Deferred](#deferred) left for later.

In a follow-up the same day: `multi-node` accepts one node; profiles are a
compute list in data, with the P family and larger fan-out in the base,
disabled until their quotas are raised; images in a private ECR repository;
versioned schemas; and the three reference runs in the base, run by the
spike and verified by the owner.
