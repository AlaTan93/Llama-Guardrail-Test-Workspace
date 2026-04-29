import atexit
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyrit.executor.attack.core.attack_config import AttackScoringConfig
from pyrit.prompt_target import OpenAIChatTarget
from pyrit.scenario import ScenarioResult
from pyrit.scenario.printer.console_printer import ConsoleScenarioResultPrinter
from pyrit.scenario.scenarios.foundry import RedTeamAgent
from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestionPaths
from pyrit.setup import IN_MEMORY, initialize_pyrit_async
from pyrit.datasets import SeedDatasetProvider
from pyrit.models import SeedGroup
from pyrit.scenario import DatasetConfiguration

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None

RAW_FIELDS = [
    "objective", "last_response", "strategy", "conversation_id",
    "executed_turns", "execution_time_ms", "pyrit_outcome", "pyrit_outcome_reason",
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


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_run_results(scenario_result: ScenarioResult) -> str:
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
    run_name = f"run_{ts}"

    results_dir = Path(__file__).parent.parent / "results" / run_name
    os.makedirs(results_dir, exist_ok=True)

    raw_rows: list[dict] = []
    for strategy, results in scenario_result.attack_results.items():
        for r in results:
            raw_rows.append({
                "objective": r.objective,
                "last_response": r.last_response.original_value if r.last_response else "",
                "strategy": strategy,
                "conversation_id": r.conversation_id,
                "executed_turns": r.executed_turns,
                "execution_time_ms": r.execution_time_ms,
                "pyrit_outcome": r.outcome.value,
                "pyrit_outcome_reason": r.outcome_reason or "",
            })

    _write_csv(results_dir / "raw_responses.csv", raw_rows, RAW_FIELDS)
    print(f"Results written to {results_dir}")
    return run_name


async def run_attacks(dataset_size: int = 400, victim_endpoint: str | None = None, victim_model: str | None = None) -> str:
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, initializers=[])  # type: ignore

    _ = _start_litellm_proxy()

    if victim_endpoint:
        objective_target = OpenAIChatTarget(
            endpoint=victim_endpoint,
            api_key="not-needed",
            model_name=victim_model or "llama3",
        )
    else:
        objective_target = OpenAIChatTarget()
    printer = ConsoleScenarioResultPrinter()

    datasets = await SeedDatasetProvider.fetch_datasets_async(dataset_names=["harmbench"])  # type: ignore
    seed_groups: list[SeedGroup] = datasets[0].seed_groups  # type: ignore

    dataset_config = DatasetConfiguration(seed_groups=seed_groups, max_dataset_size=dataset_size)

    scenario_strategies = [
    ]

    objective_scorer = SelfAskTrueFalseScorer(
        chat_target=OpenAIChatTarget(),
        true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
    )
    attack_scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)

    foundry_scenario = RedTeamAgent(attack_scoring_config=attack_scoring_config, include_baseline=True)
    await foundry_scenario.initialize_async(  # type: ignore
        objective_target=objective_target,
        scenario_strategies=scenario_strategies,
        max_concurrency=10,
        dataset_config=dataset_config,
    )

    print(f"Created scenario: {foundry_scenario.name}")
    print(f"Number of atomic attacks: {foundry_scenario.atomic_attack_count}")

    scenario_result = await foundry_scenario.run_async()  # type: ignore

    run_name = write_run_results(scenario_result)

    await printer.print_summary_async(scenario_result)  # type: ignore

    return run_name
