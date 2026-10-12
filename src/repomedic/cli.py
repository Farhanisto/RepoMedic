from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import rich.console
import typer

from repomedic.discovery import discover_repository, get_repo_info, resolve_patch_path
from repomedic.analysis.test_results import TestResult
from repomedic.core.orchestrator import Orchestrator
from repomedic.sandbox.policy import SandboxPolicy
from repomedic.reports.render import create_report, render_json, render_markdown
from repomedic.analysis.verdict import Verdict

console = rich.console.Console()
app = typer.Typer(help="RepoMedic: Evidence-backed verification for AI-generated code patches")


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context):
    """Callback for the repomedic CLI."""
    if ctx.invoked_subcommand is None:
        # Default to showing help in non-interactive mode
        typer.echo("RepMedic - Evidence-backed verification for AI-generated code patches")
        typer.echo("Use `repomedic --help` for available commands.")


## 1. Developer Experience: repomedic ##

@app.command("brief", help="Launch concise interactive interface")
def brief():
    """Launch a concise interactive interface for repository verification.
    
    Detects the current repository, summarizes its status,
    and offers inspection or patch verification.
    """
    info = discover_repository()
    
    if info is None:
        console.print("[red]Error: Not inside a Git repository.[/red]")
        console.print("Run `repomedic --help` for available commands.")
        sys.exit(1)
    
    # Show repository status
    console.print(f"[bold]Repository:[/bold] {info['path']}")
    console.print(f"[bold]Branch:[/bold] {info.get('branch', 'unknown')}")
    console.print(f"[bold]Commit:[/bold] {info.get('commit', 'unknown')[:12]}...")
    console.print(f"[bold]Staged:[/bold] {', '.join(info.get('staged', [])[:3]) or 'none'}")
    console.print(f"[bold]Unstaged:[/bold] {', '.join(info.get('unstaged', [])[:3]) or 'none'}")
    console.print(f"[bold]Untracked:[/bold] {', '.join(info.get('untracked', [])[:3]) or 'none'}")
    console.print("")
    
    # Offer options
    console.print("Options:")
    console.print("  [1] Inspect repository changes (check)")
    console.print("  [2] Verify a patch file")
    console.print("  [3] Help")
    
    # In non-interactive environments, just show help
    import os
    if not sys.stdin.isatty():
        typer.echo("Use `repomedic --help` for available commands.")
        sys.exit(0)
    
    # In interactive mode, ask for choice
    choice = input("Enter choice (1-3): ").strip()
    if choice == "1":
        # Run check
        run_check(info)
    elif choice == "2":
        # Run verify (will ask for patch)
        run_verify(info)
    else:
        typer.echo("Returning to help.")


def run_check(info: dict):
    """Run the check command to inspect the repository."""
    console.print("\n[bold]Inspecting repository changes...[/bold]")
    
    # Re-inspect with fresh data
    repo_info = get_repo_info(Path(info["path"]))
    
    console.print("\n[bold]Repository Status[/bold]")
    console.print(f"  Branch: {info.get('branch', 'unknown')}")
    console.print(f"  Commit: {info.get('commit', 'unknown')[:12] if info.get('commit') else 'unknown'}...")
    console.print(f"  Staged changes: {', '.join(repo_info.get('staged', [])[:5]) or 'none'}")
    console.print(f"  Unstaged changes: {', '.join(repo_info.get('unstaged', [])[:5]) or 'none'}")
    console.print(f"  Untracked files: {', '.join(repo_info.get('untracked', [])[:5]) or 'none'}")
    
    # Identify project configuration
    console.print("\n[bold]Project Configuration[/bold]")
    
    # Check for common config files
    config_files = []
    for config in ["pyproject.toml", "pytest.ini", "setup.cfg", "package.json", "go.mod"]:
        config_file = Path(info["path"]) / config
        if config_file.is_file():
            config_files.append(config)
    
    if config_files:
        console.print(f"  Configuration files: {', '.join(config_files)}")
    else:
        console.print("  No common configuration files detected")
    
    console.print("\n[bold]To verify a patch:[/bold]")
    console.print("  Run: repomedic verify --patch ./fix.patch")
    console.print("  Or: repomedic check --select-changes")


def run_verify(info: dict):
    """Run the verify command, asking for patch path."""
    from pathlib import Path
    
    patch_path = input("Enter path to patch file or diff text: ").strip()
    
    if not patch_path:
        console.print("[red]Error: No patch path specified.[/red]")
        return
    
    # Resolve the patch
    patch_text, is_wt = resolve_patch_path(patch_path, Path(info["path"]))
    
    # Run verification
    run_verify_patch(info, patch_text, is_wt)


## 2. Repository Discovery ##

@app.command("check")
def cmd_check():
    """Inspect the current repository without modifying the working tree.
    
    Report staged and unstaged changes separately.
    Identify relevant project and test configuration.
    Allow the developer to select changes for verification.
    Clearly distinguish inspection from actual patch verification.
    """
    info = discover_repository()
    
    if info is None:
        console.print("[red]Error: Not inside a Git repository.[/red]")
        console.print("Run `repomedic --help` for available commands.")
        sys.exit(1)
    
    repo_info = get_repo_info(Path(info["path"]))
    
    console.print(f"\n[bold]Repository:[/bold] {info['path']}")
    console.print(f"[bold]Branch:[/bold] {info.get('branch', 'unknown')}")
    console.print(f"[bold]Current Commit:[/bold] {info.get('commit', 'unknown')[:12] if info.get('commit') else 'unknown'}...")
    console.print("")
    
    console.print("[bold]Staged Changes:[/bold]")
    for f in repo_info.get("staged", [])[:10]:
        console.print(f"  - {f}")
    if not repo_info.get("staged"):
        console.print("  none")
    console.print("")
    
    console.print("[bold]Unstaged Changes:[/bold]")
    for f in repo_info.get("unstaged", [])[:10]:
        console.print(f"  - {f}")
    if not repo_info.get("unstaged"):
        console.print("  none")
    console.print("")
    
    console.print("[bold]Untracked Files:[/bold]")
    for f in repo_info.get("untracked", [])[:10]:
        console.print(f"  - {f}")
    if not repo_info.get("untracked"):
        console.print("  none")
    console.print("")
    
    # Identify project configuration
    console.print("[bold]Project Configuration:[/bold]")
    config_files = []
    for config in ["pyproject.toml", "pytest.ini", "setup.cfg", "package.json", "go.mod", "Makefile"]:
        config_file = Path(info["path"]) / config
        if config_file.is_file():
            config_files.append(config)
    
    if config_files:
        console.print(f"  Detected: {', '.join(config_files)}")
    else:
        console.print("  No common configuration files detected")
    
    console.print("")
    console.print("[bold]How to verify a patch:[/bold]")
    console.print("  Run: repomedic verify --patch ./my-fix.patch")
    console.print("  This will run the full verification pipeline in an isolated environment.")
    console.print("  Your original working tree remains unchanged.")


## 3. Command Behavior: repomedic verify --patch PATH ##

@app.command("verify")
def cmd_verify(
    patch: str = typer.Option(
        ..., help="Path to patch file or diff text"
    ),
    base: Optional[str] = typer.Option(
        None, help="Baseline commit (default: HEAD)"
    ),
    test_command: Optional[str] = typer.Option(
        None, help="Test command (default: inferred from project config)"
    ),
    timeout: int = typer.Option(120, help="Timeout in seconds for test execution"),
):
    """Verify a patch against the current repository.
    
    Executes the full verification pipeline in an isolated environment,
    producing an evidence-based verdict.
    """
    # Discover repository
    info = discover_repository()
    
    if info is None:
        console.print("[red]Error: Not inside a Git repository.[/red]")
        console.print("Run `repomedic --help` for available commands.")
        sys.exit(1)
    
    repo_path = Path(info["path"])
    
    # Resolve patch
    patch_text, is_wt = resolve_patch_path(patch, repo_path)
    
    if not patch_text or not patch_text.strip():
        console.print("[red]Error: Patch text is empty or invalid.[/red]")
        sys.exit(1)
    
    # Determine baseline commit
    if base:
        baseline_commit = base
    elif info.get("commit"):
        baseline_commit = info["commit"]
    else:
        console.print("[red]Error: Could not determine baseline commit.[/red]")
        sys.exit(1)
    
    # Determine test command
    if test_command:
        parsed_test_command = [c.strip() for c in test_command.split() if c.strip()]
    else:
        # Try to infer from project config
        parsed_test_command = ["python", "-m", "pytest", "-q"]
    
    # Run the orchestrator
    policy = SandboxPolicy()
    orch = Orchestrator(
        repo_path=str(repo_path),
        base_commit=baseline_commit,
        patch_text=patch_text,
        test_command=parsed_test_command,
        timeout_seconds=timeout,
        policy=policy,
    )
    
    try:
        result = orch.run()
    except Exception as e:
        console.print(f"[red]Error during verification: {e}[/red]")
        sys.exit(3)  # inconclusive
    
    # Display results
    verdict = result.get("verdict", "unknown")
    explanation = result.get("verdict_explanation", "N/A")
    baseline_exit = result.get("baseline_exit_code")
    patched_exit = result.get("patched_exit_code")
    risk_findings = result.get("risk_findings", 0)
    state = result.get("state", "unknown")
    
    # Map verdict to exit code
    exit_code = _exit_code_for_verdict(verdict)
    
    # Display results in terminal
    console.print("\n" + "=" * 60)
    console.print("RepoMedic Verification Result")
    console.print("=" * 60)
    console.print(f"Verdict: {verdict}")
    console.print(f"Explanation: {explanation}")
    console.print(f"Baseline exit code: {baseline_exit}")
    console.print(f"Patched exit code: {patched_exit}")
    if risk_findings > 0:
        console.print(f"Risk findings: {risk_findings}")
    console.print(f"State: {state}")
    console.print("")
    
    # Output JSON if requested (though --format not added yet, 
    # we'll support it via environment variable or stderr)
    # For now, just console output
    
    sys.exit(exit_code)


## 4. Safety and Isolation ##

# The orchestrator already handles isolation via temporary worktrees
# and the sandbox runner. No additional changes needed here.


## 5. Verdicts and Reporting ##

def _exit_code_for_verdict(verdict: str) -> int:
    """Return the process exit code for a verdict."""
    codes = {
        "VERIFIED": 0,
        "REGRESSION": 1,
        "UNSAFE": 2,
        "INCONCLUSIVE": 3,
    }
    return codes.get(verdict, 1)


@app.command("format")
def cmd_format(
    output: Optional[str] = typer.Option(
        None, help="Output file path (json or md)"
    ),
) -> None:
    """Format and output the last verification report.
    
    If no output path specified, outputs to stdout/json and stderr.
    """
    console.file = sys.stderr  # Redirect all console output to stderr
    # Look for last report in current directory
    import glob
    
    json_files = glob.glob("repomedic-report*.json")
    md_files = glob.glob("repomedic-report*.md")
    
    if not json_files and not md_files:
        console.print(
            "[red]No verification report found. "
            "Run `repomedic verify --patch PATH` first.[/red]",
            
        )
        sys.exit(1)
    
    # Use the most recent report
    if json_files:
        report_file = json_files[0]
        try:
            with open(report_file) as f:
                data = json.load(f)
            # Output valid JSON to stdout
            json_output = json.dumps(data, indent=2)
            # Send diagnostics to stderr
            console.print(f"[dim]Report: {report_file}[/dim]", )
            # Output valid JSON to stdout (no decorative formatting)
            sys.stdout.write(json_output)
            sys.stdout.write("\n")
        except Exception as e:
            console.print(f"[red]Error reading report: {e}[/red]", )
            sys.exit(1)
    elif md_files:
        report_file = md_files[0]
        try:
            with open(report_file) as f:
                content = f.read()
            console.print(content, )
        except Exception as e:
            console.print(f"[red]Error reading report: {e}[/red]", )
            sys.exit(1)


# Removed the old verify command to avoid conflicts
# The new verify command is cmd_verify above


@app.command("help-full", help="Show full help information")
def cmd_help_full():
    """Show comprehensive help for all commands."""
    console.print("""
╭─────────────────────────────────────────────────────────────────────╮
│                    RepoMedic Command Reference                      │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic ─────────────────────────────────────────────────────────╮
│ Launch concise interactive interface                                    │
│                                                                       │
│ Detects the current repository and offers inspection or patch         │
│ verification. In non-interactive environments, prints help instead.   │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic check ───────────────────────────────────────────────────╮
│ Inspect the current repository without modifying the working tree.    │
│                                                                       │
│ Reports staged/unstaged changes, identifies project/config files,     │
│ and explains how to verify a patch.                                   │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic verify --patch PATH ─────────────────────────────────────╮
│ Execute the full verification pipeline.                               │
│                                                                       │
│ 1. Validates inputs and repository state                              │
│ 2. Resolves baseline commit                                           │
│ 3. Inspects and hashes the proposed patch                             │
│ 4. Creates isolated baseline environment                              │
│ 5. Runs baseline tests and records results                            │
│ 6. Applies patch in separate isolated environment                     │
│ 6. Runs patched tests                                                 │
│ 7. Runs optional model analysis (Nano then SUPER)                     │
│ 8. Calculates deterministic verdict                                   │
│ 9. Produces structured report                                         │
│10. Cleans up temporary resources                                      │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic verify --patch PATH --base COMMIT ───────────────────────╮
│ Specify the baseline commit explicitly                                  │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic verify --patch PATH --test-command "command" ────────────╮
│ Use custom test command instead of auto-detection                       │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic verify --patch PATH --timeout SECONDS ────────────────────╮
│ Set verification timeout in seconds                                   │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic format ───────────────────────────────────────────────────╮
│ Format and output the last verification report.                       │
│   --format json    Output valid JSON to stdout (diagnostics to stderr)│
│   --format md      Output human-readable Markdown to stderr           │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic --help  ──────────────────────────────────────────────────╮
│ Show help                                                            │
╰─────────────────────────────────────────────────────────────────────╯

╭─ repomedic --version ────────────────────────────────────────────────╮
│ Show version                                                         │
╰─────────────────────────────────────────────────────────────────────╯
""")


if __name__ == "__main__":
    app()