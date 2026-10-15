---
name: testing
description: >
  State what tests must show: one named test per acceptance criterion,
  hermetic tests that pass in parallel, external resources named after the
  branch or run, paid and live-service tests kept out of normal CI, and the
  checks and tolerances numerical code needs. Use when writing or changing
  tests, or deciding what a change's tests must cover.
---

# Testing

Tests are how a reviewer checks that a PR does what its issue asks. This skill
says what the tests must show, not how to arrive at them: write them before or
after the code. Telling agents to follow a process such as test-driven
development made little difference, while tests that state concrete expected
behaviour did help (finding F4 in `docs/template-plan.md`).

## One named test per acceptance criterion

- Each acceptance criterion in the issue or approved plan has its own test,
  named for the behaviour it checks, for example
  `test_lint_fails_when_public_function_has_no_doc_comment`.
- The test asserts a concrete result: given these inputs, this output or this
  error. A test that only checks the code runs, or that would still pass with
  the change reverted, doesn't cover the criterion.
- "Verified" in the PR body pairs each criterion with its test. A
  criterion no automated test can check, such as how a page looks, names the
  manual check instead.
- Use the test runner the language already has. The `ponytail` rule's single
  runnable check is the minimum for logic no criterion covers; acceptance
  criteria are explicitly requested, so each still gets its own test.

## Hermetic tests that pass in parallel

A hermetic test depends only on its own inputs: no shared files, ports,
databases, or test order. Every test passes when the suite runs in parallel
and in any order.

- Write files only under a temporary directory the test creates.
- Seed every random number generator.
- Bind port 0 and use the port the operating system assigns, never a fixed
  port.

## External resources

Every external resource a test or job creates, such as a storage bucket, a
compute job, or an experiment-tracker run, has the branch name or the CI run
ID in its name, so parallel agents and CI runs can't collide and anything left
behind can be traced to its source. Use `git branch --show-current` locally
and `GITHUB_RUN_ID` in CI, where the checkout has no branch. Replace `/` and
any other character the service rejects. A test deletes what it creates, even
when it fails.

## Paid and live-service tests

A test that costs money or calls a live service runs only when a person or the
issue asks for it, never in normal CI. Mark it `live`, so that `mise run test`
skips it, and say under "Verified" when it ran.

| Language | Mark the test | Run only the `live` tests |
|---|---|---|
| Python | `@pytest.mark.live` | `mise run test:python -- -m live` |
| Rust | `#[ignore = "live: costs money or calls a live service"]` | `mise run test:rust -- -- --ignored` |
| TypeScript | `test("…", { tags: ["live"] }, () => { … })` | `mise exec -- pnpm exec vitest run --tags-filter live` |
| C and C++ | `set_tests_properties(<test> PROPERTIES LABELS live)` in `CMakeLists.txt` | `mise run test:cpp -- -L live -LE '^$'` |

`cargo test` skips ignored tests with no configuration; `--ignored` runs every
ignored test, not only `live` ones. The other runners need configuration that
the template doesn't have yet, which the language's first `live` test adds:

- **Python:** in `[tool.pytest]` in `pyproject.toml`, add `"-m", "not live"`
  to `addopts`, and `markers = ["live: costs money or calls a live service"]`.
  `strict = true` fails a test whose marker isn't registered.
- **TypeScript:** a root `vitest.config.ts` that defines the tag, since vitest
  fails a test whose tag isn't defined:
  `defineConfig({ test: { tags: [{ name: "live", description: "costs money or calls a live service" }] } })`.
  Add `--tags-filter '!live'` to `test:typescript` in
  `.config/mise/conf.d/typescript.toml`, and the new
  file to the `typescript` output of the `changes` job in `ci.yml`. Vitest
  combines several `--tags-filter` flags with AND, so the `live` tests run
  through vitest directly, not `mise run`.
- **C and C++:** add `"filter": { "exclude": { "label": "^live$" } }` to the
  `sanitizers` test preset in `CMakePresets.json`. `-L live` alone finds no
  tests, because the preset still excludes them; `-LE '^$'` replaces that
  exclusion with one that matches no test.

## Numerical code

These checks catch the most errors in numerical code. Use each that applies.

- **Convergence rate.** The error shrinks at the expected rate as the step
  size `h` (time step or grid spacing) shrinks. For a method of order `p`,
  `e(h) ≈ C h^p`, so the observed order `log2(e(h) / e(h/2))` matches `p`
  within a stated tolerance over at least three step sizes. Without an exact
  solution, use differences between successive refinements:
  `log2(‖u(h) - u(h/2)‖ / ‖u(h/2) - u(h/4)‖)`. Choose step sizes small enough
  that higher-order terms are negligible, and large enough that round-off
  doesn't dominate.
- **Conserved quantities.** Energy, mass, momentum, and any other quantity the
  problem conserves stay within a stated bound over a stated run, for example
  relative energy error below `1e-6` over `10^4` steps. The bound is at
  round-off level for a quantity the scheme conserves exactly, and at
  truncation-error level for one it conserves only approximately.
- **Exact solutions.** Results match known exact solutions, such as the
  harmonic oscillator or a single Fourier mode of the heat equation. Where
  none is known, choose a solution, derive the source term that makes it
  exact, and solve with that source (the method of manufactured solutions).
- **Symmetries.** Results respect the problem's symmetries. For example,
  rotating or translating the input rotates or translates the output, and
  relabelling identical particles changes nothing.

Compare floating-point values with stated tolerances, never exact equality:
`|actual - expected| <= atol + rtol * |expected|`, which is what
`numpy.testing.assert_allclose` checks. Each tolerance is a named constant
whose comment says where it comes from, such as the truncation error estimate
or a multiple of machine epsilon.
