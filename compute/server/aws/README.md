# IAM policies

The IAM policies of the server's AWS account, `agent-jobs`, in `us-east-1`,
which `compute-server:provision` (PR 13 in `docs/compute-jobs.md`) creates
after replacing two placeholders: `<account_id>`, the 12-digit account ID,
and `<bucket>`, the archive's bucket. A `${...}` is an IAM policy variable,
which AWS fills in per request. `policies_test.py` checks the actions,
resources, prefixes, and trust conditions statically; whether AWS evaluates
them as written only the real account shows. A resource of `"*"` appears only
where AWS supports nothing narrower, and in the deny policy.

## `launcher.json`: the role `compute-jobs-launcher`

The server pod's identity, through IAM Roles for Service Accounts; `eksctl`
creates its trust in PR 13. The EC2 statements are SkyPilot's
[minimal policy](https://docs.skypilot.co/en/latest/cloud-setup/cloud-permissions/aws.html)
in one region, with `compute-jobs-job`, which the admin policy forces as
`remote_identity`, in place of `skypilot-v1`.

| Sid | Why |
|---|---|
| `RunInstancesFromPublicImages` | Launching from an AMI another account owns, such as SkyPilot's |
| `RunInstancesInAccount` | The instance, its network interface, subnet, volume, and security group that a launch creates or uses |
| `TagAtLaunch` | Tagging a new instance and its volumes, only inside the `RunInstances` that creates them |
| `ManageSkyPilotInstances` | Tagging, stopping, restarting, and terminating only instances tagged `ray-cluster-name`, so never the EKS node that runs the server. SkyPilot 0.14.0 tags every instance it launches with it and selects by it before each of these calls (`sky/provision/aws/instance.py`) |
| `DescribeEc2` | Reading instances, images, subnets, and offerings; describe actions support no resource ARN |
| `CreateSecurityGroups` | The security group SkyPilot creates for a cluster, and its SSH rule |
| `CreateSpotServiceLinkedRole` | The service-linked role EC2 needs before the account's first spot request |
| `ReadJobRole` | Finding the job role and its instance profile, to attach to each machine |
| `PassJobRoleToEc2` | Attaching the job role to machines, and to nothing but EC2 |
| `FindBucket` | Checking that the bucket exists and where it is, for `jobs.bucket` and the checkpoint mount |
| `StoreUploads` | Managed jobs' uploaded working trees, under `uploads/` (`jobs.bucket`) |
| `ResolveImageDigests` | Turning the image tag a job asks for into its digest, in `compute-jobs/job` only |

## `job.json` and `job-trust.json`: the role `compute-jobs-job`

Every job machine's identity. Its `aws:userid`, `<role id>:<instance id>`,
is the machine id in the archive's `machines/<machine id>/` ("Archive
layout" in `docs/compute-jobs.md`), so a machine writes only its own files.

| Sid | Why |
|---|---|
| `ListArchive` | Listing the bucket, for checkpoints and `index/` |
| `ReadArchive` | Reading any object: the uploaded working tree, checkpoints, and other jobs' results |
| `WriteOwnMachine` | Writing under this machine's own `machines/${aws:userid}/` |
| `WriteIndexMarkers` | Writing the empty marker `index/<job name>/<machine id>`. The job name can't be scoped, so a job can write any `index/*` marker, including one under another job's name; markers aren't authoritative ("Progress" in `docs/compute-jobs.md`), and an authoritative `index/` from EC2 tags is deferred |
| `WriteCheckpoints` | Writing and deleting checkpoints under `checkpoints/`; a job could overwrite another's, costing at most a restart |
| `AuthenticateToEcr` | The registry login that every pull needs; it supports no resource ARN |
| `PullJobImage` | Pulling the image from `compute-jobs/job`, and no other repository |
| `EndOwnInstance` | Stopping or terminating the machine the request comes from, and no other; unverified until the spike |
| `Ec2InstancesAssumeJobRole` | The trust policy: EC2 instances assume the role |

## `observer.json`: the IAM user `compute-jobs-observer`

The read-only key agents hold as `COMPUTE_JOBS_AWS_ACCESS_KEY_ID` and
`COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`, so `observe` reads the archive. It has
only the job role's `ListArchive` and `ReadArchive`.

## `deny-launch.json`: the policy `compute-jobs-deny-launch`

The daily budget's action attaches it to `compute-jobs-launcher` at 100% of
actual cost ("Setup for the owner", step 9). Its one statement,
`DenyStartingMachines`, overrides any Allow; it stops no running machine.

## `image-push.json` and `image-push-trust.json`: the role `compute-jobs-image-push`

Assumed by `compute-image.yml` with GitHub's OIDC token. The trust matches
the `sub` claim exactly, so only a job in this repository's `release`
environment can assume it. That claim names the environment, not the ref
([GitHub](https://docs.github.com/en/actions/reference/security/oidc)), so
the limit to `v*` tags is the environment's own ("Setup for the owner", step
8). It also has the job role's `AuthenticateToEcr`.

| Sid | Why |
|---|---|
| `PushJobImage` | Pushing layers and the manifest to `compute-jobs/job`, and no other repository; pulling the pushed digest back, to smoke-test it before attesting, and reading its manifest to add the release tag |
| `ReleaseEnvironmentAssumesPushRole` | The trust policy: GitHub's OIDC provider, audience `sts.amazonaws.com`, `sub` `repo:arjunbhargava/foundation-compute:environment:release` |
