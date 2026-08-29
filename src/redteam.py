"""Attack orchestration: run PyRIT's RedTeamAgent against the victim model.

Pure PyRIT concerns live here — dataset loading, objective filtering, the
scenario run.  Persistence of the resulting rows (new runs and in-place
re-attack merges) is delegated to :mod:`src.runs_io`.
"""

from pyrit.datasets import SeedDatasetProvider
from pyrit.executor.attack.core.attack_config import AttackScoringConfig
from pyrit.models import SeedGroup
from pyrit.prompt_target import OpenAIChatTarget
from pyrit.scenario import DatasetConfiguration
from pyrit.scenario.printer.console_printer import ConsoleScenarioResultPrinter
from pyrit.scenario.scenarios.foundry import FoundryStrategy, RedTeamAgent
from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestionPaths
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

from src import runs_io
from src.config import LITELLM_ENDPOINT


def filter_seed_groups(seed_groups: list[SeedGroup], objectives: list[str]) -> tuple[list[SeedGroup], list[str]]:
    """Filter seed groups down to those whose objective text is in *objectives*.

    Returns ``(filtered_groups, missing_objectives)``.
    """
    wanted = set(objectives)
    filtered = []
    matched: set[str] = set()
    for g in seed_groups:
        obj = g.objective
        if obj is not None and obj.value in wanted:
            filtered.append(g)
            matched.add(obj.value)
    missing = [o for o in objectives if o not in matched]
    return filtered, missing


async def run_attacks(
    dataset_size: int = 400,
    victim_model_name: str = "victim-llama",
    objectives: list[str] | None = None,
    run_dir: str | None = None,
    tier: str | None = None,
    victim: dict | None = None,
    progress=None,
) -> str:
    """Run attacks against the victim model.

    New run: returns the created ``run_<ts>`` name (``run_dir`` is None).
    Re-attack: pass *objectives* (subset of HarmBench objective texts) and the
    existing *run_dir*; matching rows are replaced in-place (with backups).
    *victim* is the provenance block from ``src/victim_meta.py`` (stored in
    meta.json; refreshed on re-attack).
    *progress* (optional) is a :class:`src.progress.ProgressReporter`.
    """
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, initializers=[])  # type: ignore

    objective_target = OpenAIChatTarget(
        endpoint=LITELLM_ENDPOINT,
        api_key="not-needed",
        model_name=victim_model_name,
    )
    printer = ConsoleScenarioResultPrinter()

    datasets = await SeedDatasetProvider.fetch_datasets_async(dataset_names=["harmbench"])  # type: ignore
    seed_groups: list[SeedGroup] = datasets[0].seed_groups  # type: ignore

    if objectives is not None:
        seed_groups, missing = filter_seed_groups(seed_groups, objectives)
        if missing:
            print(f"WARNING: {len(missing)} requested objectives not in HarmBench dataset:")
            for m in missing[:5]:
                print(f"  - {m[:80]}")
            if len(missing) > 5:
                print(f"  ... and {len(missing) - 5} more")
        if not seed_groups:
            raise ValueError("No requested objectives matched the HarmBench dataset")
        dataset_config = DatasetConfiguration(seed_groups=seed_groups)
        effective_size = len(seed_groups)
    else:
        dataset_config = DatasetConfiguration(seed_groups=seed_groups, max_dataset_size=dataset_size)
        effective_size = dataset_size

    scenario_strategies = [
        FoundryStrategy.Url
    ]

    objective_scorer = SelfAskTrueFalseScorer(
        chat_target=OpenAIChatTarget(
            endpoint=LITELLM_ENDPOINT,
            api_key="not-needed",
            model_name=victim_model_name,
            temperature=0.1,
        ),
        true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
    )
    attack_scoring_config = AttackScoringConfig(objective_scorer=objective_scorer)

    foundry_scenario = RedTeamAgent(attack_scoring_config=attack_scoring_config, include_baseline=False)
    await foundry_scenario.initialize_async(  # type: ignore
        objective_target=objective_target,
        scenario_strategies=scenario_strategies,
        max_concurrency=10,
        dataset_config=dataset_config,
    )

    print(f"Created scenario: {foundry_scenario.name}")
    print(f"Number of atomic attacks: {foundry_scenario.atomic_attack_count}")
    if progress:
        progress.attack_total(foundry_scenario.atomic_attack_count)

    scenario_result = await foundry_scenario.run_async()  # type: ignore
    raw_rows = runs_io.rows_from_scenario(scenario_result)

    if run_dir is not None:
        runs_io.merge_into_run(raw_rows, run_dir, victim)
        run_name = run_dir.rstrip("/").split("/")[-1]
    else:
        run_name = runs_io.write_new_run(
            raw_rows,
            tier=tier,
            dataset_size=effective_size,
            victim_model_name=victim_model_name,
            victim=victim,
        )

    if progress:
        progress.attack_done(len(raw_rows))

    await printer.print_summary_async(scenario_result)  # type: ignore

    return run_name
