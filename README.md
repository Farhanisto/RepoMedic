# RepoMedic
Evidence-backed verification for AI-generated code patches

## Overview

RepoMedic verifies whether a proposed code patch fixes a reported bug, introduces regressions, or cannot be verified. It works by:

1. **Accepting** a Git repository and a patch (diff text or file path)
2. **Recording** the base commit and inspecting the patch
3. **Running** baseline tests in an isolated environment
4. **Applying** the patch to a separate clean workspace
5. **Running** the same tests after the patch
6. **Comparing** results and producing a deterministic verdict
7. **Generating** Markdown and JSON reports with evidence and uncertainty

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd repomedic

# Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Quick Start

### 1. Check a repository

```bash
repomedic check
```

Outputs repository information, staged/unstaged changes, and how to verify a patch.

### 2. Verify a patch

```bash
repomedic verify --patch "./my-fix.patch"
```

Or provide the diff text directly:

```bash
repomedic verify --patch "--- a/app.py
+++ b/app.py
@@ -1,4 +1,4 @@
 def get_page(items: list[str], page: int, page_size: int) -> list[str]:
-    start = page * page_size
+    start = (page - 1) * page_size"
```

The verification pipeline will:
- Discover the repository and current commit
- Run baseline tests (before patch)
- Apply the patch in an isolated environment
- Run tests after the patch
- Produce a verdict: `VERIFIED`, `REGRESSION`, `UNSAFE`, or `INCONCLUSIVE`
- Write a report file (`repomedic-report-<timestamp>.json`)

### 3. Format and output the report

```bash
# Output as JSON to stdout (diagnostics to stderr)
repomedic format --output report.json

# Output as Markdown to stderr (report content to stdout)
repomedic format --output report.md
```

### 4. Brief interactive interface

```bash
repomedic brief
```

Launches a concise interactive interface that detects the current repository and offers inspection or patch verification.

## Commands

### `repomedic brief`
Launches concise interactive interface detecting the current repository and offering inspection or patch verification.

### `repomedic check`
Inspect the current repository without modifying the working tree. Reports:
- Repository path and branch
- Staged and unstaged changes
- Untracked files
- Detected project configuration
- How to verify a patch

### `repomedic verify --patch PATH`
Verify a patch against the current repository.

**Options:**
- `--patch` (required): Path to patch file or diff text
- `--base` (optional): Baseline commit (default: HEAD)
- `--test-command` (optional): Test command (default: `python -m pytest -q`)
- `--timeout` (optional): Timeout in seconds (default: 120)

### `repomedic format --output FORMAT`
Format and output the last verification report.

**Options:**
- `--output` (required): `json` or `md`

## Verdicts

| Verdict | Meaning |
|---------|---------|
| `VERIFIED` | The bug was reproduced at baseline and passed after the patch. No regressions. |
| `REGRESSION` | A test that passed at baseline fails after the patch. |
| `UNSAFE` | Policy blocked the patch execution or its changes are blocked. |
| `INCONCLUSIVE` | Baseline could not be reproduced, tests couldn't run, or evidence is insufficient. |

## How It Works

### Pipeline

1. **Repository Discovery**: Finds git root, branch, current commit, and repository info
2. **Patch Resolution**: Validates and resolves the patch path/text
3. **Baseline Execution**: Runs tests at the base commit in an isolated workspace
4. **Patched Execution**: Applies patch to a clean clone and runs the same tests
5. **Verdict Calculation**: Deterministic verdict based on test result comparison
6. **Report Generation**: Writes JSON/Markdown report with all evidence

### Isolation Guarantees

- **Never modifies the developer's working tree** - patches are applied to `/tmp` clones
- **Safe timeout enforcement** - test execution is killed after the configured timeout
- **Sandbox policy** - configurable policy for what changes are allowed

## Report Output

### JSON Format

```json
{
  "verdict": "VERIFIED",
  "verdict_explanation": "The patch was verified: the bug was reproduced at baseline and passed after the patch. No regressions detected.",
  "baseline_exit_code": 1,
  "patched_exit_code": null,
  "risk_findings": 0,
  "state": "REPORT_READY"
}
```

Output to **stdout**, diagnostics to **stderr**.

### Markdown Format

Renders the JSON report as human-readable Markdown.

Output to **stdout**, diagnostics to **stderr**.

## Benchmark Suite

Run the full benchmark:

```bash
python -m evaluation.run_benchmark --tasks evaluation/tasks.jsonl --timeout 30
```

Outputs verdicts for each task and aggregate metrics.

## Limitations

- **MVP only**: Currently handles single-hunk patches that replace one line in a file
- **Test inference**: Default test command is `python -m pytest -q`; customize with `--test-command`
- **No model integration yet**: Deterministic verdicts only; model-assisted analysis planned for future versions
- **Patch format**: Unified diff format expected; complex multi-file changes may not apply

## License

MIT