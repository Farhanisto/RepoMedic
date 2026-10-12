# RepoMedic: Step-by-Step Build Instructions

> **Project goal:** Build a CLI-first, Nemotron-powered verification tool that checks whether a proposed code patch fixes a reported bug, introduces regressions, or cannot be verified.
>
> **Build philosophy:** Start with deterministic verification. Add model-assisted analysis only after baseline-versus-patched test execution works reliably. Do not begin with a web UI, multi-agent framework, or fine-tuning.

---

## 0. Define the MVP

The first usable version must:

1. Accept a local Git repository and a patch file, commit, or working-tree diff.
2. Record the base commit and inspect the patch.
3. Run baseline tests in an isolated environment.
4. Apply the patch to a separate clean workspace.
5. Run the same tests after the patch.
6. Compare results and produce a deterministic verdict.
7. Use Nemotron through Nebius Token Factory to analyze patch intent, likely risks, and potential missing edge cases.
8. Write a Markdown and JSON report that includes evidence and uncertainty.

### Initial verdicts

- `verified`: the required bug reproduction was observed before the patch, passed afterward, and required regression checks passed.
- `regression`: a required test that passed at baseline fails after the patch, or the designated regression test still fails after the patch.
- `inconclusive`: the baseline could not be reproduced, tests could not run, or evidence is insufficient.
- `unsafe`: policy blocked the patch or its execution.

Keep the verdict separate from risk findings. A patch can pass tests and still have high-risk changes.

### Non-goals for the first version

- No automatic production deployments.
- No automatic pushing or merging.
- No support for every programming language.
- No model fine-tuning.
- No mandatory web dashboard.
- No unrestricted shell execution or network access in the test sandbox.

---

## 1. Set up the project

Use Python 3.11 or newer, Git, Docker, and a Nebius Token Factory API key. Confirm the current Token Factory endpoint and available Nemotron model IDs in the official account/catalog documentation before coding; do not assume a model ID from an example is available to your account.

Create the project:

```bash
mkdir repomedic
cd repomedic
git init

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install typer rich pydantic pydantic-settings openai pytest pytest-json-report
pip install ruff mypy
```

Create the package and test folders:

```bash
mkdir -p src/repomedic/{core,repository,analysis,models,sandbox,reports}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p evaluation
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "repomedic"
version = "0.1.0"
description = "Evidence-backed verification for AI-generated code patches"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "rich>=13",
  "pydantic>=2",
  "pydantic-settings>=2",
  "openai>=1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-json-report>=1", "ruff>=0.5", "mypy>=1"]

[project.scripts]
repomedic = "repomedic.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
```

Install the package in editable mode:

```bash
pip install -e ".[dev]"
```

Add `.env` to `.gitignore`; commit `.env.example`, never credentials.

**Done when:** `python -c "import repomedic"` succeeds after adding `src/repomedic/__init__.py`, and `repomedic --help` works after the CLI is created.

---

## 2. Create a known-bug fixture

Create `tests/fixtures/pagination_demo/app.py`:

```python
def get_page(items: list[str], page: int, page_size: int) -> list[str]:
    """Return a 1-indexed page."""
    start = page * page_size  # Deliberate bug: page is 1-indexed.
    return items[start : start + page_size]
```

Create `tests/fixtures/pagination_demo/test_app.py`:

```python
from app import get_page


def test_first_page_starts_at_zero():
    assert get_page(["a", "b", "c", "d"], 1, 2) == ["a", "b"]


def test_second_page_starts_after_first_page():
    assert get_page(["a", "b", "c", "d"], 2, 2) == ["c", "d"]
```

Initialize the fixture as a Git repository and commit the buggy baseline:

```bash
cd tests/fixtures/pagination_demo
git init
git add app.py test_app.py
git commit -m "Add deliberately buggy pagination example"
cd ../../..
```

Verify that the baseline test fails:

```bash
cd tests/fixtures/pagination_demo
python -m pytest -q
cd ../../..
```

Keep the baseline fixture unchanged in the test suite. Create a separate fixed patch as a fixture or generate it during an integration test.

**Done when:** at least one known regression test fails before the fix and passes after a correct fix. This known expected behavior will validate the verdict engine.

---

## 3. Implement configuration and shared schemas

Create `src/repomedic/config.py`:

- Read API credentials from environment variables.
- Read model IDs from environment variables.
- Configure maximum runtime, memory, output size, retry count, and allowed test runners.
- Never print secrets in logs or reports.

Example `.env.example`:

```dotenv
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.us-central1.nebius.com/v1/
NEMOTRON_NANO_MODEL=
NEMOTRON_SUPER_MODEL=
NEMOTRON_ULTRA_MODEL=
REPOMEDIC_MAX_ATTEMPTS=2
REPOMEDIC_TEST_TIMEOUT_SECONDS=120
```

Treat the endpoint above as a configuration example and verify it against the current Token Factory documentation for your account.

Create `src/repomedic/analysis/schemas.py` (or a shared `models.py`) with Pydantic types for:

- `VerificationRequest`: repository path, patch source, base commit, optional issue description, and a validated test command.
- `TestResult`: phase (`baseline` or `patched`), exit code, timeout flag, passed/failed/skipped counts, and output excerpt.
- `RiskFinding`: stable rule ID, severity, message, and evidence.
- `VerificationReport`: run ID, base commit, patch hash, results, verdict, findings, evidence summary, model usage, and unresolved questions.

Use enumerated types for verdicts and severity. Keep raw test output available as a bounded artifact; avoid storing unbounded logs in a JSON report.

**Done when:** schema unit tests reject invalid verdict values, malformed required fields, and invalid test-command forms.

---

## 4. Implement Git and patch handling

Create `src/repomedic/repository/git.py` and `diff.py`.

Implement small, testable functions:

- `get_head_commit(repo_path)`: return the current commit SHA.
- `get_working_tree_status(repo_path)`: record staged, unstaged, and untracked changes.
- `export_patch(repo_path, source)`: create a patch from a supported input source.
- `validate_patch(patch_text)`: parse and reject malformed patches.
- `hash_patch(patch_text)`: calculate a stable SHA-256 hash.
- `list_changed_paths(patch_text)`: return normalized changed paths.
- `check_patch_scope(paths, policy)`: flag disallowed paths and suspicious changes.

Rules:

1. Never silently discard the developer's uncommitted changes.
2. Record the original commit and working-tree state before doing anything.
3. Reject absolute paths, path traversal, and changes outside the disposable workspace.
4. Treat submodules, symlinks, binary patches, Git hooks, and submodule URL changes as unsupported or blocked in the MVP unless explicitly handled.
5. Do not execute scripts or commands discovered in a repository merely because the model suggests them.
6. Use subprocess argument arrays, not shell string interpolation.

Prefer creating a fresh Git worktree or a temporary clone for every verification run. The baseline and patched versions must be independent and must not share writable source files.

**Done when:** unit tests cover valid diffs, malformed diffs, path traversal, protected files, empty patches, and repositories with uncommitted user changes.

---

## 5. Implement isolated test execution

Create `src/repomedic/sandbox/runner.py` and `policy.py`.

Define a runner interface such as:

```python
from typing import Protocol


class TestRunner(Protocol):
    def run(self, workspace: str, command: list[str], timeout_seconds: int):
        ...
```

The concrete Docker runner should:

- Start from an approved, pinned image.
- Mount only the disposable workspace.
- Run as a non-root user.
- Drop Linux capabilities and use `no-new-privileges`.
- Set CPU, memory, PID, disk, and time limits.
- Disable network access during test execution by default.
- Never mount the Docker socket or host home directory.
- Never pass the Token Factory API key or other host secrets into the container.
- Bound captured stdout/stderr.
- Kill timed-out processes and remove containers/workspaces afterward.

Dependency installation is a separate, controlled preparation step. Do not give test code unrestricted network access to download arbitrary dependencies during execution.

For the MVP, support Python projects using a prebuilt image with the required Python version and pytest. If a project needs additional dependencies, either build an approved image ahead of time or return `inconclusive` with a clear explanation. Do not silently loosen sandbox restrictions.

Use an explicit executable and argument list, e.g. `["python", "-m", "pytest", "-q"]`; do not accept arbitrary shell strings from a CLI argument, repository file, or model response.

**Done when:** integration tests prove that a timeout is enforced, output is capped, network access is disabled, and host credentials are unavailable in the sandbox. If those security properties have not been verified, do not advertise the runner as safe for untrusted repositories.

---

## 6. Implement baseline-versus-patched execution

Create `src/repomedic/analysis/test_results.py`.

Workflow:

1. Prepare a clean baseline workspace at the recorded base commit.
2. Run the approved baseline test command and capture the structured result.
3. Prepare a separate clean patched workspace from the same base commit.
4. Apply the validated patch.
5. Run the same approved test command in the patched workspace.
6. Compare test identities and outcomes where structured test reports are available.
7. Preserve both logs and workspace metadata as evidence.

Do not infer success solely from output text. Use process exit status and structured test-runner reports where possible. Distinguish:
- Assertion/test failures.
- Test collection errors.
- Missing dependencies.
- Timeouts.
- Infrastructure errors.
- Successful test execution.

A whole-suite run is useful but not enough to prove the reported bug is fixed. The request should identify a reproduction test or a known expected behavior. In the MVP, require a supplied regression test or a configured test selector for a strong `verified` verdict.

**Done when:** test fixtures cover baseline failure + patched pass, baseline pass + patched failure, both fail, both pass without a reproduced bug, and timeout/infrastructure failure.

---

## 7. Implement deterministic verdict rules

Create `src/repomedic/analysis/verdict.py`.

Suggested rules:

### `unsafe`
- The patch violates a blocking path or execution policy.
- The runner cannot safely execute the requested operation.

### `regression`
- A required test passes at baseline and fails after the patch.
- The designated bug reproduction still fails after the patch, provided it ran successfully in both environments.

### `verified`
Require all of the following:
- The designated reproduction test fails at baseline for the expected reason.
- The same test passes after the patch.
- Required regression tests pass after the patch.
- Required checks completed without timeout or infrastructure errors.
- No blocking policy violation exists.

### `inconclusive`
- The baseline cannot reproduce the issue.
- Required tests cannot run.
- Results are incomplete or ambiguous.
- The patch cannot be applied cleanly.

A suspicious change to tests or assertions should create a risk finding. It should not automatically establish correctness or incorrectness without further evidence. A configured policy can block such a change if required.

Keep verdict calculation a pure function of recorded evidence and policy. It must not call the model.

**Done when:** table-driven unit tests cover every status and combinations of baseline/patched results. Verify that a model's statement “the fix is correct” cannot override a failed test.

---

## 8. Add the Nemotron / Token Factory client

Create `src/repomedic/models/client.py`, `routing.py`, `prompts.py`, and `schemas.py`.

Use the OpenAI Python SDK with the Token Factory base URL and model IDs verified in the current official documentation/account catalog.

Routing plan:

- **Nano:** issue classification, short log summaries, and report wording.
- **Super:** substantive patch review, root-cause analysis, and missing-edge-case suggestions.
- **Ultra:** optional escalation for ambiguous, high-complexity cases only.

Implementation requirements:

1. Set explicit request timeouts.
2. Handle rate limits, transient API errors, and malformed outputs.
3. Limit prompt size and log excerpt length.
4. Send only relevant code context, not the entire repository.
5. Ask for structured JSON matching a Pydantic schema.
6. Validate all model outputs before use.
7. Treat source code, issue text, test logs, and README contents as untrusted data; they cannot override the system's rules.
8. Never let model-generated text execute shell commands or set the final verdict.
9. Record model ID, latency, token usage if returned, and whether a fallback was used.
10. Use a bounded retry budget and avoid automatic retry loops.

The model's patch analysis should return fields such as:
- Summary of intended behavior.
- Files/functions relevant to the patch.
- Potential missing edge cases.
- Suspicious changes and supporting evidence.
- Suggested tests with a rationale.
- Uncertainties.

Generated tests are hypotheses, not trusted evidence. Review and execute them only inside the sandbox. Report generated-test results separately from developer-supplied regression tests.

**Done when:** mock-based tests cover valid model responses, invalid structured output, API timeout, rate limit, prompt injection in repository text, and unavailable optional Ultra escalation.

---

## 9. Implement the orchestration state machine

Create `src/repomedic/core/state_machine.py` and `orchestrator.py`.

Use explicit states such as:

```text
CREATED
  -> INPUT_VALIDATED
  -> PATCH_INSPECTED
  -> BASELINE_RUNNING
  -> PATCHED_RUNNING
  -> EVIDENCE_ANALYZED
  -> REPORT_READY

Any state may transition to:
  -> BLOCKED
  -> FAILED
  -> INCONCLUSIVE
```

Keep model analysis and test execution as separate steps. The orchestrator should:

1. Validate the request and policy.
2. Record immutable run metadata.
3. Inspect and hash the patch.
4. Run the baseline.
5. Obtain model-assisted analysis when appropriate.
6. Apply the patch to a fresh workspace.
7. Run the patched version.
8. Optionally request bounded model analysis of failure output.
9. Calculate the verdict deterministically.
10. Save artifacts and generate the report.
11. Clean up temporary workspaces even after exceptions.

For an initial implementation, use a maximum of two model-assisted repair/review attempts and an overall wall-clock budget. Remember: the core product verifies patches; automatic patch generation is optional and should not delay the MVP.

**Done when:** a single function can execute the complete pipeline with dependency-injected Git, runner, model client, and report writer. Unit tests should use fakes; only integration tests should call Docker or Token Factory.

---

## 10. Create the CLI

Create `src/repomedic/cli.py` using Typer and Rich.

Suggested commands:

```bash
repomedic --help

# Verify a patch file against a repository
repomedic verify --repo ./my-repo --diff ./changes.patch

# Verify working-tree changes
repomedic verify --repo ./my-repo --working-tree

# Use an explicitly supplied regression test selector
repomedic verify --repo ./my-repo --diff ./changes.patch   --test-selector tests/test_pagination.py::test_second_page

# Save JSON and Markdown reports
repomedic verify --repo ./my-repo --diff ./changes.patch   --output ./repomedic-report
```

These are proposed command interfaces; implement and document the exact syntax consistently.

The CLI should display:
- Current verification phase.
- Baseline and patched test summaries.
- Key risk findings.
- Final verdict and its evidence.
- Report file locations.

Use meaningful process exit codes so CI can interpret results. For example, success for verified, a distinct code for regression, and separate codes for inconclusive and blocked/unsafe. Document the codes before integrating with CI.

**Done when:** CLI integration tests cover valid inputs, missing files, invalid patches, all verdicts, and report output. Avoid printing API keys or unrestricted raw logs.

---

## 11. Build Markdown and JSON reports

Create `src/repomedic/reports/render.py`.

Each report should contain:

- Run ID and timestamp.
- Repository identity and base commit.
- Patch SHA-256 hash and changed-file list.
- Runtime, test runner and verification-policy versions.
- Baseline and patched test results.
- Commands executed and their exit statuses.
- Verdict and explanation.
- Risk findings with evidence.
- Model IDs, latency and token usage where available.
- Incomplete checks and unresolved questions.
- References to bounded log artifacts.

Never claim that all tests passed if only a subset ran. Do not describe a patch as proven correct; say which checks passed and which were not performed.

**Done when:** the same saved evidence produces stable JSON and Markdown reports, and reports can be regenerated without making new model calls.

---

## 12. Create the benchmark

Create `evaluation/tasks.jsonl` and `evaluation/run_benchmark.py`.

Start with 10–20 small Python bug tasks. Each task should specify:
- Repository fixture and base commit.
- Patch to evaluate.
- Bug description.
- Required reproduction test or selector.
- Expected baseline behavior.
- Expected patched behavior.
- Known risk flags, where relevant.

Include diverse cases:
1. Correct patch that fixes the bug.
2. Patch that leaves the bug unfixed.
3. Patch that breaks a previously passing test.
4. Patch that weakens or skips a test.
5. Patch with unrelated file changes.
6. Patch that cannot be applied.
7. Baseline environment failure.
8. Timeout.
9. Edge-case failure.
10. Patch with suspicious but non-blocking risk.

Measure:
- Correct `verified` verdicts.
- Incorrect `verified` verdicts.
- Regressions caught.
- Inconclusive rate.
- False-positive risk findings.
- End-to-end latency.
- Model calls and token usage.
- Cost, when pricing and usage data are available.

Do not report accuracy without defining the denominator. Preserve each task's result, including failures. Avoid selecting only tasks that the system already handles well.

**Done when:** one command runs the benchmark and produces aggregate JSON/Markdown metrics plus per-task evidence.

---

## 13. Security and reliability checklist

Before allowing arbitrary public repositories, verify:

- [ ] Test commands are allowlisted and represented as argument arrays.
- [ ] Repository-controlled code runs only in disposable isolated environments.
- [ ] Containers run non-root with restricted capabilities and resource limits.
- [ ] Network access is disabled during tests by default.
- [ ] Host credentials and the Docker socket are not mounted into the sandbox.
- [ ] Patches cannot escape the workspace or modify host files.
- [ ] Git hooks and repository setup scripts are not automatically executed on the host.
- [ ] Submodules, symlinks, binary patches, and unsupported file types are blocked or explicitly handled.
- [ ] Logs and model context are size-limited and sanitized.
- [ ] Temporary containers and workspaces are cleaned up.
- [ ] Timeouts and cancellation work.
- [ ] Model outputs cannot execute commands or override verdict rules.
- [ ] Original user changes remain untouched.
- [ ] A security test suite checks the sandbox's actual behavior.

Docker is useful isolation, but is not a guarantee of security by itself. For higher-risk multi-tenant use, evaluate stronger sandboxing and host hardening before offering a public service.

---

## 14. Suggested build schedule

### Day 1 — Deterministic foundation
- Set up the package.
- Create the known-bug fixture.
- Implement Git snapshotting, diff parsing, and patch hashing.
- Run baseline and patched tests locally using a disposable workspace.

### Day 2 — Verdict engine and sandbox
- Implement Docker-based test execution and resource limits.
- Implement test result parsing and deterministic verdict rules.
- Add unit and integration tests for edge cases.

### Day 3 — Nemotron integration
- Configure Token Factory credentials and verified model IDs.
- Implement structured patch analysis.
- Add Nano/Super routing and optional Ultra escalation.
- Test API failures and prompt-injection-resistant handling.

### Day 4 — CLI and reports
- Implement `repomedic verify`.
- Produce Markdown and JSON reports.
- Add meaningful exit codes and clean error handling.
- Run an end-to-end demo on the fixture.

### Day 5 — Benchmark and polish
- Add 10–20 evaluation cases.
- Measure false verification, regression detection, latency, and model usage.
- Harden sandbox controls.
- Write setup instructions and record a fallback demo.

If time is shorter, prioritize the deterministic repair-verification loop and a reproducible benchmark over UI polish or advanced agent features.

---

## 15. Final acceptance criteria

The MVP is ready to demonstrate when:

1. A known-bug baseline fails its designated regression test.
2. A correct patch makes that same test pass.
3. A bad patch that leaves the bug unfixed is not marked verified.
4. A patch that introduces a regression is flagged.
5. Infrastructure errors and timeouts produce `inconclusive`, not false success.
6. A policy-violating patch is blocked before execution.
7. Nemotron provides useful, validated analysis through Token Factory.
8. The final verdict is determined by recorded evidence and explicit rules, not the model's opinion.
9. A developer can run one CLI command and receive a reproducible report.
10. The benchmark publishes results for all test tasks, including failures.

**Build this in order:** patch handling → isolated baseline/patched execution → verdict engine → Nemotron analysis → CLI/reporting → benchmark. This order minimizes the risk of spending hackathon time on an impressive agent interface before the core claim is proven.
