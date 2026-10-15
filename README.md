# foundation-compute

The infra half of a compute-jobs system for agents: a shared SkyPilot API
server on EKS, a client package (`compute_jobs_cli`), an in-job wrapper,
and an S3 job archive.

```sh
bash .cursor/install.sh   # install mise and the pinned tools, once
mise run check            # everything CI runs: lint, tests, docs
mise run fmt              # format in place
mise run docs             # build the documentation site
```

[AGENTS.md](AGENTS.md) lists every command and where code lives.
[docs/orchestration.md](docs/orchestration.md) says how orchestrator agents
launch workers.
