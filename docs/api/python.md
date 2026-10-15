# Python

sphinx-autoapi generates the Python API reference from the docstrings in
each distribution's `src/`, which it parses without importing the packages:
`compute_jobs_cli`, the client, from `src/`; `compute_jobs`, the library job
code imports, from `lib/src/`; and `compute_jobs_admin_policy`, the server's
admin policy, from `compute/server/admin_policy/src/`.

```{toctree}
:maxdepth: 1

<<<<<<< before updating
python/compute_jobs_cli/index
python/compute_jobs/index
python/compute_jobs_admin_policy/index
=======
python/foundation_compute/index
>>>>>>> after updating
```
