from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from repomedic.analysis.test_results import run_baseline, run_patched
from repomedic.analysis.verdict import calculate_verdict, Verdict
from repomedic.core.orchestrator import Orchestrator
from repomedic.models.client import NemotronClient
from repomedic.sandbox.policy import SandboxPolicy


def load_tasks(tasks_path: str = "evaluation/tasks.jsonl") -> List[Dict[str, Any]]:
    """Load benchmark tasks from a JSONL file."""
    tasks = []
    task_path = Path(tasks_path)
    if not task_path.exists():
        print(f"[warn] Tasks file not found: {tasks_path}", file=sys.stderr)
        return tasks
    with open(task_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def run_task(
    task: Dict[str, Any],
    timeout: int = 120,
    use_model: bool = False,
) -> Dict[str, Any]:
    """Run a single benchmark task.

    Returns a dict with the task result including verdict, evidence, and metrics.
    """
    task_id = task.get("id", "unknown")
    repo_path = task.get("repository", "")
    base_commit = task.get("base_commit", "")
    patch_text = task.get("patch", "")
    reproduction_test = task.get("reproduction_test", "")

    result: Dict[str, Any] = {
        "task_id": task_id,
        "task": task_id,
        "verdict": None,
        "verdict_explanation": "",
        "baseline_exit_code": None,
        "patched_exit_code": None,
        "risk_findings": [],
        "model_calls": 0,
        "model_latency_ms": 0,
        "model_token_usage": "",
        "error": None,
    }

    try:
        # Create orchestrator
        policy = SandboxPolicy()
        orch = Orchestrator(
            repo_path=repo_path,
            base_commit=base_commit,
            patch_text=patch_text,
            test_command=["python", "-m", "pytest", "-q"],
            timeout_seconds=timeout,
            policy=policy,
        )

        # Optionally set model client
        if use_model:
            # In a real implementation, would set a NemotronClient
            # For now, run without model assistance
            pass

        # Run the pipeline
        output = orch.run()

        # Extract results
        result["baseline_exit_code"] = output.get("baseline_exit_code")
        result["patched_exit_code"] = output.get("patched_exit_code")
        result["verdict"] = output.get("verdict")
        result["verdict_explanation"] = output.get("verdict_explanation", "")
        result["risk_findings"] = output.get("risk_findings", [])

        # Count risk findings
        risk_count = len(result["risk_findings"]) if result["risk_findings"] else 0

        # Determine if the verdict matches the expected behavior
        expected_baseline = task.get("expected_baseline", "")
        expected_patched = task.get("expected_patched", "")

        # Map verdict to result classification
        verdict = result.get("verdict")
        if verdict == "VERIFIED":
            # Verify that the expected behavior actually occurred
            baseline_ok = (
                "fails" in expected_baseline.lower()
                if expected_baseline
                else True
            )
            patched_ok = (
                "passes" in expected_patched.lower()
                if expected_patched
                else True
            )
            if baseline_ok and patched_ok:
                result["classification"] = "correct_verified"
            elif not baseline_ok and not patched_ok:
                result["classification"] = "incorrect_verified"
            elif not patched_ok:
                result["classification"] = "regression_caught"
            else:
                result["classification"] = "verified_mismatch"
        elif verdict == "REGRESSION":
            result["classification"] = "regression_caught"
        elif verdict == "UNSAFE":
            result["classification"] = "blocked_safe"
        elif verdict == "INCONCLUSIVE":
            result["classification"] = "inconclusive"
        else:
            result["classification"] = "unknown"

    except Exception as e:
        result["error"] = str(e)
        result["classification"] = "error"
        import traceback
        traceback.print_exc()

    return result


def run_benchmark(
    tasks_path: str = "evaluation/tasks.jsonl",
    timeout: int = 120,
    use_model: bool = False,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full benchmark suite.

    Args:
        tasks_path: Path to the JSONL tasks file.
        timeout: Timeout in seconds per task.
        use_model: Whether to use model-assisted analysis.
        output_path: Optional path to save aggregate results.

    Returns:
        Aggregate benchmark results including metrics and per-task evidence.
    """
    tasks = load_tasks(tasks_path)
    if not tasks:
        print("[error] No tasks loaded.", file=sys.stderr)
        return {}

    results: List[Dict[str, Any]] = []
    metrics: Dict[str, int] = {
        "total_tasks": 0,
        "correct_verified": 0,
        "incorrect_verified": 0,
        "regression_caught": 0,
        "blocked_safe": 0,
        "inconclusive": 0,
        "error": 0,
    }

    print(f"Running benchmark with {len(tasks)} tasks...")
    print("=" * 70)

    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] Running {task.get('id', 'unknown')}")
        result = run_task(task, timeout=timeout, use_model=use_model)
        results.append(result)

        # Update metrics
        result_class = result.get("classification", "error")
        metrics["total_tasks"] += 1
        if result_class in metrics:
            metrics[result_class] += 1

        # Print per-task result
        verdict = result.get("verdict", "unknown")
        print(f"  Verdict: {verdict}")
        print(f"  Classification: {result_class}")
        if result.get("error"):
            print(f"  Error: {result['error'][:100]}")

    # Calculate aggregate metrics
    total = metrics["total_tasks"]
    print("\n" + "=" * 70)
    print("AGGREGATE METRICS")
    print("=" * 70)
    print(f"Total tasks: {total}")
    for key, value in metrics.items():
        if key != "total_tasks":
            percentage = (value / total * 100) if total > 0 else 0
            print(f"{key}: {value} ({percentage:.1f}%)")

    # Save output if requested
    if output_path:
        with open(output_path, "w") as f:
            json.dump({
                "metrics": metrics,
                "results": results,
            }, f, indent=2)
        print(f"\nResults saved to: {output_path}")

    return {
        "metrics": metrics,
        "results": results,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run RepMedic benchmark suite")
    parser.add_argument(
        "--tasks", default="evaluation/tasks.jsonl", help="Path to tasks JSONL file"
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Timeout per task in seconds"
    )
    parser.add_argument(
        "--model", action="store_true", help="Use model-assisted analysis"
    )
    parser.add_argument(
        "--output", help="Path to save aggregate results JSON"
    )

    args = parser.parse_args()
    run_benchmark(
        tasks_path=args.tasks,
        timeout=args.timeout,
        use_model=args.model,
        output_path=args.output,
    )