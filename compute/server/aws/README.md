# IAM policies

The IAM policies of the shared server's AWS account, `agent-jobs`, as JSON
that `compute-server:provision` (PR 13 in `docs/compute-jobs.md`) creates.
Each file has two placeholders, which provisioning replaces: `<account_id>`,
the account's 12-digit ID, and `<bucket>`, the archive's S3 bucket. A
`${...}` is an IAM policy variable, which AWS fills in at request time, and
stays as written. Everything is in `us-east-1`.

`policies_test.py` checks the files statically: the actions, resources,
prefixes, and trust conditions below. No test can check that AWS evaluates
them as written; `compute-server:status` and the spike do that on the real
account.

A wildcard resource, `"*"`, appears only where AWS supports no narrower one:
`ec2:Describe*` and `ecr:GetAuthorizationToken`, and the deny policy, which
must cover every instance.

## `launcher.json`: the role `compute-jobs-launcher`

The server's identity, given to its pod through IAM Roles for Service
Accounts; `eksctl` creates the role and its trust in the cluster's OIDC
provider in PR 13. The EC2 statements are SkyPilot's
[minimal policy](https://docs.skypilot.co/en/latest/cloud-setup/cloud-permissions/aws.html),
narrowed to one region, and its `skypilot-v1` role replaced by
`compute-jobs-job`, which the admin policy forces as `remote_identity`.

| Sid | Why |
|---|---|
| `RunInstancesFromPublicImages` | Launching from an AMI another account owns, such as SkyPilot's |
| `RunInstancesInAccount` | The instance, its network interface, subnet, volume, and security group that a launch creates or uses |
| `ManageInstances` | Tagging the job's machines, and stopping, restarting, and terminating them |
| `TagVolumes` | Tagging the machines' volumes; without it SkyPilot warns and leaves them untagged |
| `DescribeEc2` | Reading instances, images, subnets, and offerings; describe actions support no resource ARN |
| `CreateSecurityGroups` | The security group SkyPilot creates for a cluster, and its SSH rule |
| `CreateSpotServiceLinkedRole` | The service-linked role EC2 needs before the account's first spot request |
| `ReadJobRole` | Finding the job role and its instance profile, to attach to each machine |
| `PassJobRoleToEc2` | Attaching the job role to machines, and to nothing but EC2 |
| `FindBucket` | Checking that the bucket exists and where it is, for `jobs.bucket` and the checkpoint mount |
| `StoreUploads` | Managed jobs' uploaded working trees, under `uploads/` (`jobs.bucket`) |
| `ResolveImageDigests` | Turning the image tag a job asks for into its digest, in `compute-jobs/job` only |

## `job.json` and `job-trust.json`: the role `compute-jobs-job`

The identity of every job machine, through its instance profile. Its
`aws:userid` is `<role id>:<instance id>`, the machine id that names the
archive's `machines/<machine id>/`, so a machine can write only its own
record, progress, output, and log ("Archive layout" in `docs/compute-jobs.md`).

| Sid | Why |
|---|---|
| `ListArchive` | Listing the bucket, for checkpoints and `index/` |
| `ReadArchive` | Reading any object: the uploaded working tree, checkpoints, and other jobs' results |
| `WriteOwnMachine` | Writing under this machine's own `machines/${aws:userid}/` |
| `WriteIndexMarkers` | Writing the empty marker `index/<job name>/<machine id>`; the job name can't be scoped, so a job could write another's marker |
| `WriteCheckpoints` | Writing and deleting checkpoints under `checkpoints/`; a job could overwrite another's, costing at most a restart |
| `AuthenticateToEcr` | The registry login that every pull needs; it supports no resource ARN |
| `PullJobImage` | Pulling the image from `compute-jobs/job`, and no other repository |
| `EndOwnInstance` | Stopping or terminating the machine the request comes from, and no other; unverified until the spike |
| `Ec2InstancesAssumeJobRole` | The trust policy: EC2 instances assume the role |

## `observer.json`: the IAM user `compute-jobs-observer`

The read-only key agents hold as `COMPUTE_JOBS_AWS_ACCESS_KEY_ID` and
`COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`, so `observe` reads the archive when the
server is down. It exposes job logs and outputs, nothing more.

| Sid | Why |
|---|---|
| `ListArchive` | Listing `index/` and each machine's files |
| `ReadArchive` | Reading progress, run records, results, and logs |

## `deny-launch.json`: the policy `compute-jobs-deny-launch`

The daily budget's action attaches it to `compute-jobs-launcher` at 100% of
actual cost ("Setup for the owner", step 9). It blocks new machines and
stops none.

| Sid | Why |
|---|---|
| `DenyStartingMachines` | No new or restarted machine, whatever any other policy allows |

## `image-push.json` and `image-push-trust.json`: the role `compute-jobs-image-push`

Assumed by `compute-image.yml` with GitHub's OIDC token, to push a release's
image. The trust matches the token's `sub` claim exactly, so only a job in
this repository's `release` environment can assume it; the environment
itself allows only `v*` tags ("Setup for the owner", step 8), because the
`sub` claim of a job in an environment names the environment, not the ref
([GitHub](https://docs.github.com/en/actions/reference/security/oidc)).

| Sid | Why |
|---|---|
| `AuthenticateToEcr` | The registry login that every push needs; it supports no resource ARN |
| `PushJobImage` | Pushing layers and the manifest to `compute-jobs/job`, and no other repository |
| `ReleaseEnvironmentAssumesPushRole` | The trust policy: GitHub's OIDC provider, audience `sts.amazonaws.com`, `sub` `repo:arjunbhargava/foundation-compute:environment:release` |
