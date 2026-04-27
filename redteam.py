import asyncio
import atexit
import csv
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyrit.prompt_target import OpenAIChatTarget
from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestionPaths, TrueFalseInverterScorer
from pyrit.executor.attack.core.attack_config import AttackScoringConfig
from pyrit.scenario import ScenarioCompositeStrategy, ScenarioResult
from pyrit.scenario.printer.console_printer import ConsoleScenarioResultPrinter
from pyrit.scenario.scenarios.foundry import FoundryStrategy, RedTeamAgent
from pyrit.setup import IN_MEMORY, initialize_pyrit_async
from pyrit.datasets import SeedDatasetProvider
from pyrit.models import SeedGroup
from pyrit.models.attack_result import AttackOutcome
from pyrit.scenario import DatasetConfiguration

ANIMALS = [
    "ant", "bear", "bee", "bird", "bison", "cat", "cobra", "crane", "crow",
    "deer", "dog", "dove", "duck", "eagle", "fox", "frog", "goat", "hare",
    "hawk", "horse", "jaguar", "koala", "leopard", "lion", "lynx", "moose",
    "otter", "owl", "panda", "panther", "parrot", "penguin", "rabbit", "raven",
    "salmon", "seal", "shark", "snake", "sparrow", "swan", "tiger", "wolf",
]

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None

RESULT_FIELDS = [
    "objective", "outcome", "outcome_reason", "executed_turns",
    "execution_time_ms", "conversation_id", "last_response", "strategy",
]
STAT_FIELDS = [
    "run_name", "datetime", "total_attacks", "successes", "failures",
    "undetermined", "success_rate_pct", "failure_rate_pct",
    "undetermined_rate_pct", "avg_execution_time_ms", "avg_turns",
    "strategies_used",
]

LITELLM_PORT = 4000
LITELLM_CONFIG = str(Path(__file__).parent / "litellm_config.yaml")
SCORER_MODEL = "claude-haiku-4.5"
PROXY_STARTUP_TIMEOUT = 60


def _start_litellm_proxy() -> subprocess.Popen:
    litellm_bin = str(Path(sys.executable).parent / "litellm")
    proc = subprocess.Popen(
        [litellm_bin, "--config", LITELLM_CONFIG, "--port", str(LITELLM_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    atexit.register(proc.terminate)

    print(f"Starting LiteLLM proxy on port {LITELLM_PORT} ...")
    deadline = time.monotonic() + PROXY_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if httpx is not None:
                resp = httpx.get(f"http://127.0.0.1:{LITELLM_PORT}/health", timeout=2)
                if resp.status_code == 200:
                    print("LiteLLM proxy is ready.")
                    return proc
            else:
                urllib.request.urlopen(f"http://127.0.0.1:{LITELLM_PORT}/health", timeout=2)
                print("LiteLLM proxy is ready.")
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode() if proc.stdout else ""
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"LiteLLM proxy exited early.\nstdout: {stdout}\nstderr: {stderr}")
        time.sleep(1)

    proc.terminate()
    raise RuntimeError(f"LiteLLM proxy did not become healthy within {PROXY_STARTUP_TIMEOUT}s")


def _result_to_row(result, strategy: str) -> dict:
    return {
        "objective": result.objective,
        "outcome": result.outcome.value,
        "outcome_reason": result.outcome_reason or "",
        "executed_turns": result.executed_turns,
        "execution_time_ms": result.execution_time_ms,
        "conversation_id": result.conversation_id,
        "last_response": result.last_response.original_value if result.last_response else "",
        "strategy": strategy,
    }


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_run_results(scenario_result: ScenarioResult) -> str:
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
    animal = random.choice(ANIMALS)
    run_name = f"{animal}_{ts}"

    results_dir = Path(__file__).parent / "results" / run_name
    os.makedirs(results_dir, exist_ok=True)

    all_rows: list[dict] = []
    for strategy, results in scenario_result.attack_results.items():
        for r in results:
            all_rows.append(_result_to_row(r, strategy))

    successes = [r for r in all_rows if r["outcome"] == "success"]
    failures = [r for r in all_rows if r["outcome"] == "failure"]
    undetermined = [r for r in all_rows if r["outcome"] == "undetermined"]

    _write_csv(results_dir / "successes.csv", successes, RESULT_FIELDS)
    _write_csv(results_dir / "failures.csv", failures, RESULT_FIELDS)
    _write_csv(results_dir / "undetermined.csv", undetermined, RESULT_FIELDS)

    total = len(all_rows) or 1
    stats = {
        "run_name": run_name,
        "datetime": now.isoformat(),
        "total_attacks": len(all_rows),
        "successes": len(successes),
        "failures": len(failures),
        "undetermined": len(undetermined),
        "success_rate_pct": round(len(successes) / total * 100, 2),
        "failure_rate_pct": round(len(failures) / total * 100, 2),
        "undetermined_rate_pct": round(len(undetermined) / total * 100, 2),
        "avg_execution_time_ms": round(sum(r["execution_time_ms"] for r in all_rows) / total, 2),
        "avg_turns": round(sum(r["executed_turns"] for r in all_rows) / total, 2),
        "strategies_used": "; ".join(scenario_result.get_strategies_used()),
    }
    _write_csv(results_dir / "statistics.csv", [stats], STAT_FIELDS)

    print(f"Results written to {results_dir}")
    return run_name


async def main():
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, initializers=[])  # type: ignore

    _ = _start_litellm_proxy()

    objective_target = OpenAIChatTarget()
    printer = ConsoleScenarioResultPrinter()

    scorer_target = OpenAIChatTarget(
        endpoint=f"http://127.0.0.1:{LITELLM_PORT}/v1",
        api_key="not-needed",
        model_name=SCORER_MODEL,
    )

    objective_scorer = SelfAskTrueFalseScorer(
        chat_target=scorer_target,
        true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
    )

    scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)

    datasets = await SeedDatasetProvider.fetch_datasets_async(dataset_names=["harmbench"])  # type: ignore
    seed_groups: list[SeedGroup] = datasets[0].seed_groups  # type: ignore

    dataset_config = DatasetConfiguration(seed_groups=seed_groups, max_dataset_size=10)

    scenario_strategies = [
    ]

    foundry_scenario = RedTeamAgent(attack_scoring_config=scoring_config)
    await foundry_scenario.initialize_async(  # type: ignore
        objective_target=objective_target,
        scenario_strategies=scenario_strategies,
        max_concurrency=20,
        dataset_config=dataset_config,
    )

    print(f"Created scenario: {foundry_scenario.name}")
    print(f"Number of atomic attacks: {foundry_scenario.atomic_attack_count}")

    scenario_result = await foundry_scenario.run_async()  # type: ignore

    write_run_results(scenario_result)

    await printer.print_summary_async(scenario_result)  # type: ignore

if __name__ == "__main__":
    asyncio.run(main())
