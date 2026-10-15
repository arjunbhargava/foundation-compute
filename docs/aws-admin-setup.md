# AWS administrator setup

Status: **draft for an AWS administrator**. No AWS resource exists yet.
This page tells an AWS administrator what to create in AWS so the owner can
set up compute jobs, and what permissions each step needs. It assumes you
know AWS but nothing about this project. The full design is in
[the compute jobs plan](compute-jobs.md).

Two parts of the plan are not written yet, and this page marks what depends
on them:

- **Pending PR 12**: the IAM policy files under `compute/server/aws/`, and
  `mise.admin.toml`, which pins the admin tools. Neither is on `main`.
- **Pending PR 13**: provisioning, `compute-server:provision`. Its AWS calls
  are unknown until it is written, so the permission policy below is
  **unverified**.

## What this is

- A shared [SkyPilot](https://docs.skypilot.co) API server that launches
  compute jobs (GPU simulation, ML training) for the owner's AI agents.
- It runs on Amazon EKS, with its state in RDS PostgreSQL, in one dedicated
  account, `agent-jobs`, in `us-east-1` only.
- Job machines are EC2 instances, launched on demand and deleted when the
  job ends. Results go to an S3 bucket, the **archive**.
- Job images live in an ECR repository, `compute-jobs/job`. GitHub Actions
  pushes them through an IAM role it assumes with GitHub's OIDC token, so no
  AWS key is stored in GitHub.

**Standing cost**: about $460 a month, $15 a day, for the server, whether or
not jobs run (plan, [Cost](compute-jobs.md#cost) and
[The API server](compute-jobs.md#the-api-server)). A domain, if one must be
registered, adds about $15 a year.

**Job cost**: nothing runs until the owner approves a compute budget for it.
Each job has its own `budget_usd`, which the server enforces. EC2 vCPU
quotas cap what can run at once: at the plan's quotas, at most $360.55 an
hour at list price
([Hardware profiles](compute-jobs.md#hardware-profiles)). A daily budget of
$10,000 blocks new machines when reached.

## Terms

| Term | Meaning |
|---|---|
| Owner | The person who runs this system. Lacks the AWS privileges for setup. |
| Setup window | The time between your granting access and the owner finishing setup. |
| Provisioning | `MISE_ENV=admin mise run compute-server:provision`: creates the cluster, database, bucket, roles, and server (pending PR 13). |
| eksctl | The command-line tool that creates the EKS cluster, through CloudFormation. |
| IRSA | IAM Roles for Service Accounts: a Kubernetes pod assumes an IAM role, with no stored key. |
| OIDC provider | An IAM identity provider that lets an outside service, here GitHub, assume a role with a signed token. |

## Choose an option

**Option A (recommended)**: you create the account, then give the owner a
scoped IAM Identity Center permission set for the setup window, and remove it
afterwards. The owner runs the steps.

**Option B**: you run provisioning yourself on a laptop. Prerequisites:

| Tool | Version | Where pinned |
|---|---|---|
| git, and a clone of `arjunbhargava/foundation-compute` | any | not pinned |
| mise | 2026.9.18 | `.cursor/install.sh` |
| AWS CLI v2 | pending PR 12 | `mise.admin.toml` |
| eksctl | pending PR 12 | `mise.admin.toml` |
| kubectl | pending PR 12 | `mise.admin.toml` |
| Helm | pending PR 12 | `mise.admin.toml` |

With `mise.admin.toml` in place, `MISE_ENV=admin mise install` installs the
pinned tools. You then set `COMPUTE_SERVER_ADMIN_AWS_PROFILE` to an AWS CLI
profile that signs in to `agent-jobs` with IAM Identity Center, and run the
task; it asks you to type the cluster name before it changes anything
([Admin tasks](compute-jobs.md#admin-tasks)). It prints a read-only access
key and the server's initial admin password once (pending PR 13): give them
to the owner through a password manager, never by email or chat.

In both options, only you can do step 1. The rest can be either of you.

## Steps and the permissions each needs

| # | Step | Who | Permissions |
|---|---|---|---|
| 1 | Create the account | You | `organizations:CreateAccount`, in the management account or a delegated administrator |
| 2 | Option A only: permission set and assignment | You | `sso:CreatePermissionSet`, `sso:PutInlinePolicyToPermissionSet`, `sso:AttachManagedPolicyToPermissionSet`, `sso:CreateAccountAssignment`, `sso:ProvisionPermissionSet`, and their `Delete` counterparts afterwards |
| 3 | Quotas | Either | `servicequotas:` statement `Quotas` below |
| 4 | Route 53 hosted zone | Either | statement `HostedZone`; registering a domain also needs `route53domains:RegisterDomain` (you only) |
| 5 | GitHub OIDC provider | Either | `iam:CreateOpenIDConnectProvider`, `iam:TagOpenIDConnectProvider`, in statement `EksctlAndComputeJobsIam` |
| 6 | Provisioning (pending PR 13) | Either | the two AWS managed policies and the whole inline policy below |
| 7 | Daily budget with an action | Either | statement `Budget`, and `iam:CreateRole`, `iam:PutRolePolicy`, `iam:PassRole` on `compute-jobs-budget-action` |
| 8 | Cost anomaly alert (optional) | Either | `ce:CreateAnomalyMonitor`, `ce:CreateAnomalySubscription` |

### 1. Create the account

1. Open <https://console.aws.amazon.com/organizations/v2/home/accounts> and
   choose **Add an AWS account**.
2. Name it `agent-jobs`, under the owner's negotiated pricing agreement, in
   the organizational unit you choose (see
   [Questions](#questions-for-the-administrator)).
3. Turn on IAM Identity Center access to it for the owner's user.

### 2. Option A: the permission set

1. Open <https://console.aws.amazon.com/singlesignon/home>, then
   **Permission sets** > **Create permission set** > **Custom**.
2. Name it `ComputeJobsSetup`. Session duration: 4 hours (the maximum is
   12).
3. Attach the AWS managed policies `AmazonEC2FullAccess` and
   `AWSCloudFormationFullAccess`. eksctl's documented minimum needs both
   ([eksctl](https://eksctl.io/usage/minimum-iam-policies/)).
4. Paste the [inline policy](#provisioning-policy) below, with
   `<account_id>` replaced by `agent-jobs`'s 12-digit ID.
5. Under **AWS accounts**, assign it to the owner's user in `agent-jobs`
   only.
6. Note the date. Identity Center assignments don't expire on their own, so
   remove the assignment when the owner reports setup done, or after an
   agreed date.

**What the permission set allows, plainly**: it can create IAM roles named
`compute-jobs-*` and `eksctl-*` and attach any policy to them. A principal
that can do that can grant itself any permission within the account. The
dedicated account, and your organization's SCPs, are the real boundary; a
permissions boundary would narrow it (see
[Questions](#questions-for-the-administrator)).

### 3. Quotas

The owner reports that their account already has on-demand vCPU quotas above
the plan's minimums. **Do not lower any quota.** Request an increase only
where the current value is below the minimum.

Quotas are per account. If `agent-jobs` is a new account, it starts at AWS's
defaults (0 for G and P, 5 for Standard;
[AWS](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)),
not at the owner's existing account's values, so it needs the increases.

1. Open
   <https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas>,
   in `us-east-1`, signed in to `agent-jobs`.
2. Record each current value below, and request an increase only where it
   is under the minimum.

| EC2 quota, in vCPUs | Plan's minimum | Current value in `agent-jobs` |
|---|---|---|
| Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances | 64 | `<fill in>` |
| Running On-Demand G and VT instances | 384 | `<fill in>` |
| All G and VT Spot Instance Requests | 384 | `<fill in>` |
| Running On-Demand P instances | 0 | `<fill in>` |
| All P Spot Instance Requests | 0 | `<fill in>` |

`compute/server/admin_policy/src/compute_jobs_admin_policy/limits.yaml`
mirrors these values, because they cap how many machines can run at once and
so how much can be spent in an hour. `compute-server:status` multiplies each
by the dearest instance type allowed for it and fails if the total exceeds
the $10,000 daily cap divided by 24, $416.67 an hour.

### 4. Route 53 hosted zone

1. Agree the server's host name with the owner, such as
   `skypilot.<domain>`.
2. Open <https://console.aws.amazon.com/route53/v2/hostedzones> and create
   a public hosted zone for the domain or a subdomain of it. If the domain
   lives elsewhere, delegate the subdomain with NS records there.
3. Note the hosted zone ID.

### 5. GitHub OIDC provider

1. Open <https://console.aws.amazon.com/iam/home#/identity_providers/create>.
2. Type **OpenID Connect**; URL `https://token.actions.githubusercontent.com`;
   audience `sts.amazonaws.com`.
3. Note its ARN. Only the role `compute-jobs-image-push` will trust it, and
   only for this repository's `release` environment (pending PR 12).

### 6. Provisioning (pending PR 13)

Runs on a laptop, never in CI. Per the plan it creates, in `us-east-1`:

- an EKS cluster with one m7i.2xlarge node, its VPC, and one NAT gateway,
  through eksctl's CloudFormation stacks;
- the AWS Load Balancer Controller, an Application Load Balancer, and an ACM
  certificate for the host name, validated in the hosted zone;
- RDS PostgreSQL db.t4g.micro, Multi-AZ, 20 GB, 7-day backups;
- the S3 bucket (private, 90-day expiry) and the ECR repository
  `compute-jobs/job` (immutable tags, keeps the last 10 images);
- the roles `compute-jobs-launcher` (IRSA), `compute-jobs-job`, and
  `compute-jobs-image-push`, the policy `compute-jobs-deny-launch`, and the
  IAM user `compute-jobs-observer` with one read-only access key;
- SkyPilot, installed with Helm.

### 7. Daily budget with an action

AWS Budgets runs an action through an IAM role you choose
([AWS](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-action-configure.html)).
The plan doesn't name one; this page proposes `compute-jobs-budget-action`.

1. Create the role at <https://console.aws.amazon.com/iam/home#/roles/create>:
   trusted entity **AWS service**, use case **Budgets**, and this inline
   policy (narrowed from AWS's
   [example](https://docs.aws.amazon.com/cost-management/latest/userguide/billing-example-policies.html);
   the narrowing is unverified):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
         "Resource": "arn:aws:iam::<account_id>:role/compute-jobs-launcher",
         "Condition": {
           "ArnEquals": {
             "iam:PolicyARN": "arn:aws:iam::<account_id>:policy/compute-jobs-deny-launch"
           }
         }
       }
     ]
   }
   ```

2. After provisioning, open
   <https://console.aws.amazon.com/costmanagement/home#/budgets/create>.
   Create a daily cost budget, `compute-jobs-daily`, of $10,000, with email
   alerts at 50% and 80% of actual cost.
3. Add an action at 100% of actual cost, run automatically: apply the IAM
   policy `compute-jobs-deny-launch` to the role `compute-jobs-launcher`.

### 8. Cost anomaly alert (optional)

Not in the plan. Budget data lags by up to a day, so an anomaly alert at
<https://console.aws.amazon.com/costmanagement/home#/anomaly-detection>
can warn sooner. Your call.

## Provisioning policy

The inline policy for the permission set in step 2. **Unverified until PR 13
shows which calls provisioning makes**; expect to add actions when the owner
first runs it. Its sources:

| Statements | Source |
|---|---|
| `EksctlEks`, `EksctlSsm`, `EksctlKmsAndLogs`, `EksctlAndComputeJobsIam`, `EksctlReadRolesAndUsers`, `ServiceLinkedRoles` | eksctl's `EksAllAccess` and `IamLimitedAccess` ([eksctl](https://eksctl.io/usage/minimum-iam-policies/)), with `compute-jobs-*` names added for the plan's roles and policies, and RDS's service-linked role |
| `ObserverUser`, `Database`, `Certificate`, `HostedZone`, `Archive`, `ImageRepository` | The resources the plan says provisioning creates; action lists unverified |
| `Quotas`, `Budget` | Steps 3 and 7, if the owner does them |
| `OnlyUsEast1` | Denies every regional action outside `us-east-1`; global services excepted. The pattern is AWS's [region-deny example](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_examples_general.html); the exception list is unverified |

It assumes the bucket's name starts `compute-jobs-`, which PR 13 must keep.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "EksctlEks", "Effect": "Allow", "Action": "eks:*", "Resource": "*" },
    {
      "Sid": "EksctlSsm",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters"],
      "Resource": ["arn:aws:ssm:*:<account_id>:parameter/aws/*", "arn:aws:ssm:*::parameter/aws/*"]
    },
    {
      "Sid": "EksctlKmsAndLogs",
      "Effect": "Allow",
      "Action": ["kms:CreateGrant", "kms:DescribeKey", "logs:PutRetentionPolicy"],
      "Resource": "*"
    },
    {
      "Sid": "EksctlAndComputeJobsIam",
      "Effect": "Allow",
      "Action": [
        "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile", "iam:AddRoleToInstanceProfile",
        "iam:ListInstanceProfilesForRole", "iam:GetRole", "iam:CreateRole", "iam:DeleteRole",
        "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy", "iam:PassRole",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies",
        "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
        "iam:GetPolicy", "iam:CreatePolicy", "iam:DeletePolicy", "iam:ListPolicyVersions",
        "iam:GetOpenIDConnectProvider", "iam:CreateOpenIDConnectProvider",
        "iam:DeleteOpenIDConnectProvider", "iam:TagOpenIDConnectProvider"
      ],
      "Resource": [
        "arn:aws:iam::<account_id>:instance-profile/eksctl-*",
        "arn:aws:iam::<account_id>:role/eksctl-*",
        "arn:aws:iam::<account_id>:policy/eksctl-*",
        "arn:aws:iam::<account_id>:role/eksctl-managed-*",
        "arn:aws:iam::<account_id>:role/aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup",
        "arn:aws:iam::<account_id>:oidc-provider/*",
        "arn:aws:iam::<account_id>:instance-profile/compute-jobs-*",
        "arn:aws:iam::<account_id>:role/compute-jobs-*",
        "arn:aws:iam::<account_id>:policy/compute-jobs-*"
      ]
    },
    {
      "Sid": "EksctlReadRolesAndUsers",
      "Effect": "Allow",
      "Action": ["iam:GetRole", "iam:GetUser"],
      "Resource": ["arn:aws:iam::<account_id>:role/*", "arn:aws:iam::<account_id>:user/*"]
    },
    {
      "Sid": "ServiceLinkedRoles",
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "iam:AWSServiceName": ["eks.amazonaws.com", "eks-nodegroup.amazonaws.com", "eks-fargate.amazonaws.com", "rds.amazonaws.com"]
        }
      }
    },
    {
      "Sid": "ObserverUser",
      "Effect": "Allow",
      "Action": [
        "iam:CreateUser", "iam:DeleteUser", "iam:TagUser", "iam:PutUserPolicy", "iam:DeleteUserPolicy",
        "iam:CreateAccessKey", "iam:DeleteAccessKey", "iam:ListAccessKeys"
      ],
      "Resource": "arn:aws:iam::<account_id>:user/compute-jobs-observer"
    },
    {
      "Sid": "Database",
      "Effect": "Allow",
      "Action": [
        "rds:CreateDBInstance", "rds:ModifyDBInstance", "rds:DeleteDBInstance",
        "rds:CreateDBSubnetGroup", "rds:DeleteDBSubnetGroup",
        "rds:AddTagsToResource", "rds:ListTagsForResource", "rds:Describe*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Certificate",
      "Effect": "Allow",
      "Action": ["acm:RequestCertificate", "acm:DescribeCertificate", "acm:ListCertificates", "acm:AddTagsToCertificate", "acm:DeleteCertificate"],
      "Resource": "*"
    },
    {
      "Sid": "HostedZone",
      "Effect": "Allow",
      "Action": [
        "route53:CreateHostedZone", "route53:GetHostedZone", "route53:ListHostedZones",
        "route53:ListHostedZonesByName", "route53:ListResourceRecordSets",
        "route53:ChangeResourceRecordSets", "route53:GetChange"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Archive",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket", "s3:DeleteBucket", "s3:ListBucket", "s3:GetBucket*", "s3:PutBucket*",
        "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
        "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration",
        "s3:GetObject", "s3:PutObject", "s3:DeleteObject"
      ],
      "Resource": ["arn:aws:s3:::compute-jobs-*", "arn:aws:s3:::compute-jobs-*/*"]
    },
    {
      "Sid": "ImageRepository",
      "Effect": "Allow",
      "Action": [
        "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:DescribeRepositories",
        "ecr:PutLifecyclePolicy", "ecr:GetLifecyclePolicy", "ecr:PutImageTagMutability", "ecr:TagResource"
      ],
      "Resource": "arn:aws:ecr:us-east-1:<account_id>:repository/compute-jobs/*"
    },
    {
      "Sid": "Quotas",
      "Effect": "Allow",
      "Action": [
        "servicequotas:GetServiceQuota", "servicequotas:GetAWSDefaultServiceQuota",
        "servicequotas:ListServiceQuotas", "servicequotas:RequestServiceQuotaIncrease",
        "servicequotas:ListRequestedServiceQuotaChangeHistoryByQuota"
      ],
      "Resource": "*"
    },
    { "Sid": "Budget", "Effect": "Allow", "Action": "budgets:*", "Resource": "*" },
    {
      "Sid": "OnlyUsEast1",
      "Effect": "Deny",
      "NotAction": ["iam:*", "sts:*", "route53:*", "budgets:*", "ce:*", "organizations:*", "support:*"],
      "Resource": "*",
      "Condition": { "StringNotEquals": { "aws:RequestedRegion": "us-east-1" } }
    }
  ]
}
```

## What to hand back to the owner

- [ ] Account ID of `agent-jobs`
- [ ] Region: `us-east-1`
- [ ] Hosted zone ID, and the agreed host name
- [ ] GitHub OIDC provider ARN
- [ ] IAM Identity Center start URL, and the permission set's name
  (`ComputeJobsSetup`) and its removal date (Option A)
- [ ] The quota table above, filled in
- [ ] Option B only: provisioning's output (endpoint, dashboard URL, push
  role ARN), and the read-only key and admin password through a password
  manager

None of these goes in the repository. The owner keeps the SSO profile in
`~/.aws/config` and names it in `COMPUTE_SERVER_ADMIN_AWS_PROFILE` in their
own shell. From [Credentials](compute-jobs.md#credentials), the owner later
sets:

| Where | Variables |
|---|---|
| Cursor Secrets (dashboard, Cloud Agents > Secrets) | `SKYPILOT_API_SERVER_ENDPOINT`, `SKYPILOT_SERVICE_ACCOUNT_TOKEN`, `COMPUTE_JOBS_AWS_ACCESS_KEY_ID`, `COMPUTE_JOBS_AWS_SECRET_ACCESS_KEY`, `COMPUTE_JOBS_BUCKET`, `COMPUTE_JOBS_AWS_REGION` |
| GitHub environment `release`, as variables | `COMPUTE_JOBS_ECR_PUSH_ROLE_ARN`, `COMPUTE_JOBS_AWS_REGION` |
| The owner's shell | `COMPUTE_SERVER_ADMIN_AWS_PROFILE` |

## Guardrails

- **No root access keys.** Use root only for tasks that require it.
- **No long-lived admin keys.** The owner signs in through Identity Center.
  The server uses IRSA. The one long-lived key is `compute-jobs-observer`'s,
  which can only read the bucket and is rotated quarterly.
- **`us-east-1` only.** The policy's `OnlyUsEast1` statement enforces it for
  the owner; an SCP on the account would enforce it for everyone.
- **The budget action.** At $10,000 of actual cost in a day it attaches
  `compute-jobs-deny-launch` (deny `ec2:RunInstances` and
  `ec2:StartInstances`) to the server's role. It stops no running machine,
  and AWS budget data lags by up to a day, so the quotas are the hard cap.
- **Teardown.** The plan has no teardown task, and PR 13 doesn't exist.
  Until then, in this order (unverified):
  1. `helm uninstall` the server, so the controller deletes the load
     balancer.
  2. `eksctl delete cluster --name <cluster>`, which deletes its
     CloudFormation stacks, VPC, NAT gateway, and eksctl's roles.
  3. Delete the RDS instance, the bucket (after emptying it), the ECR
     repository, the budget, the hosted zone, the OIDC provider, and every
     IAM role, policy, and user named `compute-jobs-*`.
  4. Close the account in Organizations, if nothing else uses it.

## Questions for the administrator

1. **Account**: a new account, or an existing one? If new, it won't have
   the owner's existing quotas (step 3). Which organizational unit?
2. **SCPs**: do any deny `eks:*`, `iam:CreateOpenIDConnectProvider`,
   `iam:CreateUser`, `iam:CreateAccessKey` (the read-only key), service-linked
   roles, or `us-east-1`?
3. **Permissions boundary**: should roles created in the account require
   one? eksctl supports boundaries in its config file; PR 13 would need to set
   them.
4. **Names**: do `compute-jobs-*`, `eksctl-*`, or `agent-jobs` clash with
   anything in your organization?
5. **Domain**: which domain or subdomain holds the host name, and who
   controls its DNS?
6. **After setup**: `compute-server:status` and each upgrade need access to
   the account. Should the owner keep a narrower permission set, or get
   `ComputeJobsSetup` again for each upgrade? By EKS's default, the cluster
   grants Kubernetes admin to the role that created it, an `AWSReservedSSO_*` role
   whose ARN changes if the permission set is recreated, so PR 13 should add a
   lasting cluster access entry.
