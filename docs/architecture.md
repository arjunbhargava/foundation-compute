# Architecture

Status: planned. The code is three Python distributions in one uv workspace:
the client (`compute_jobs_cli`, at the root), the library job code imports
(`compute_jobs`, in `lib/`), and the server's admin policy
(`compute_jobs_admin_policy`, in `compute/server/admin_policy/`). The admin
policy so far holds `limits.yaml`, the compute list, its validation, and the
spending-ceiling check on its quotas. The client
parses the four `compute-jobs` commands' arguments and reports each failure
with a kind (`kinds.py`); the commands' bodies are not built yet. The
library's `fanout` spreads a search job's evaluations over the job's Ray
cluster, and checkpoints and resumes the search; Ray, its one external
dependency, is the library's optional `fanout` extra. The
library never imports the client, and the admin policy imports neither,
which the import-linter contracts in `pyproject.toml` check. "Packages and
files" in [the compute jobs plan](compute-jobs.md) says what each will
contain and who installs it.

PR 15 of that plan replaces this page with the system as built. Follow the
`architecture-docs` skill: diagrams first, then system context, main data
flow, module map, invariants, and failure handling.
