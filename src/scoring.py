import argparse
import asyncio
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pyrit.models import Message, MessagePiece
from pyrit.prompt_target import OpenAIChatTarget, PromptChatTarget
from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestionPaths
from pyrit.setup import IN_MEMORY, initialize_pyrit_async

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None

LITELLM_PORT = 4000
LITELLM_CONFIG = str(Path(__file__).parent / "litellm_config.yaml")
SCORER_MODEL = "claude-haiku-4.5"
PROXY_STARTUP_TIMEOUT = 60
BF16_PORT = 8081

SCORED_FIELDS = [
    "objective", "last_response", "strategy", "conversation_id",
    "score_value", "score_rationale", "scorer_type",
    "executed_turns", "execution_time_ms", "pyrit_outcome",
]


def _sanitize_json_response(text: str) -> str:
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)
    text = re.sub(r'"score_value"\s*:\s*"True"', '"score_value": "true"', text)
    text = re.sub(r'"score_value"\s*:\s*"False"', '"score_value": "false"', text)

    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    score_match = re.search(r'"score_value"\s*:\s*"(true|false|True|False)"', text, re.IGNORECASE)
    score_value = score_match.group(1).lower() if score_match else "false"

    rationale_match = re.search(r'"rationale"\s*:\s*"', text)
    rationale = ""
    if rationale_match:
        remainder = text[rationale_match.end():]
        end_match = re.search(r'",\s*"metadata"', remainder)
        if end_match:
            rationale = remainder[:end_match.start()]
        else:
            rationale = remainder.rstrip('"}').rstrip('"')

    return json.dumps({
        "score_value": score_value,
        "description": "",
        "rationale": rationale,
        "metadata": "",
    })


class _SanitizingScorerTarget(PromptChatTarget):
    def __init__(self, target: PromptChatTarget):
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)

    async def send_prompt_async(self, *, message: Message) -> list[Message]:
        response = await self._target.send_prompt_async(message=message)
        for msg in response:
            for piece in msg.message_pieces:
                if piece.converted_value_data_type == "text" and piece.converted_value:
                    piece.converted_value = _sanitize_json_response(piece.converted_value)
        return response


def _parse_pyrit_env() -> dict[str, str]:
    env_path = Path(__file__).parent / ".pyrit" / ".env"
    result = {}
    if not env_path.exists():
        return result
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^(\w+)\s*=\s*"?(.*?)"?\s*$', line)
            if match:
                result[match.group(1)] = match.group(2)
    return result


def _sanitize_response(text: str) -> str:
    return "".join(c for c in text if c >= " " or c == " ").strip()


def _load_raw_responses(run_dir: str) -> list[dict]:
    path = Path(run_dir) / "raw_responses.csv"
    if not path.exists():
        raise FileNotFoundError(f"raw_responses.csv not found in {run_dir}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_scored_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["conversation_id"] for row in csv.DictReader(f) if row.get("conversation_id")}


def _append_scored_row(path: Path, row: dict, write_header: bool) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCORED_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _start_litellm_proxy() -> subprocess.Popen:
    litellm_bin = str(Path(sys.executable).parent / "litellm")
    proc = subprocess.Popen(
        [litellm_bin, "--config", LITELLM_CONFIG, "--port", str(LITELLM_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
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


def _make_scorer_target(scorer_type: str, pyrit_env: dict[str, str]) -> OpenAIChatTarget:
    if scorer_type == "self":
        endpoint = pyrit_env.get("OPENAI_CHAT_ENDPOINT", "http://127.0.0.1:8080/v1")
        return OpenAIChatTarget(
            endpoint=endpoint,
            api_key="not-needed",
            model_name=pyrit_env.get("OPENAI_CHAT_MODEL", "llama3"),
        )
    elif scorer_type == "bf16":
        return OpenAIChatTarget(
            endpoint=f"http://127.0.0.1:{BF16_PORT}/v1",
            api_key="not-needed",
            model_name="llama3",
        )
    elif scorer_type == "claude":
        return OpenAIChatTarget(
            endpoint=f"http://127.0.0.1:{LITELLM_PORT}/v1",
            api_key="not-needed",
            model_name=SCORER_MODEL,
        )
    else:
        raise ValueError(f"Unknown scorer type: {scorer_type}")


async def _score_responses(
    responses: list[dict],
    scorer_type: str,
    pyrit_env: dict[str, str],
    run_dir: str,
) -> None:
    output_path = Path(run_dir) / f"scored_{scorer_type}.csv"
    already_scored = _load_scored_ids(output_path)

    if already_scored:
        print(f"  [{scorer_type}] Resuming: {len(already_scored)} already scored, "
              f"{len(responses) - len(already_scored)} remaining")

    remaining = [r for r in responses if r["conversation_id"] not in already_scored]
    if not remaining:
        print(f"  [{scorer_type}] All responses already scored, skipping.")
        return

    write_header = not output_path.exists()
    target = _make_scorer_target(scorer_type, pyrit_env)
    target = _SanitizingScorerTarget(target)
    scorer = SelfAskTrueFalseScorer(
        chat_target=target,
        true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
    )

    total = len(responses)
    done = len(already_scored)

    for row in remaining:
        done += 1
        objective = row["objective"]
        last_response = _sanitize_response(row["last_response"])

        print(f"  [{scorer_type}] {done}/{total}: {objective[:60]}...")

        piece = MessagePiece(role="assistant", original_value=last_response)
        message = Message([piece])

        try:
            scores = await scorer.score_async(message, objective=objective)
            score_value = scores[0].score_value
            score_rationale = scores[0].score_rationale
        except Exception as e:
            print(f"    Scoring error: {e}")
            score_value = "error"
            score_rationale = str(e)[:500]

        scored_row = {
            "objective": objective,
            "last_response": last_response,
            "strategy": row["strategy"],
            "conversation_id": row["conversation_id"],
            "score_value": score_value,
            "score_rationale": score_rationale,
            "scorer_type": scorer_type,
            "executed_turns": row["executed_turns"],
            "execution_time_ms": row["execution_time_ms"],
            "pyrit_outcome": row["pyrit_outcome"],
        }
        _append_scored_row(output_path, scored_row, write_header)
        write_header = False

    successes = sum(
        1 for r in remaining if r.get("_scored_value") != "error"
    )
    print(f"  [{scorer_type}] Completed: {len(remaining)} responses scored")


def _count_scored(path: Path) -> dict[str, int]:
    counts = {"success": 0, "failure": 0, "error": 0, "undetermined": 0, "total": 0}
    if not path.exists():
        return counts
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            counts["total"] += 1
            val = row.get("score_value", "undetermined")
            if val == "true":
                counts["success"] += 1
            elif val == "false":
                counts["failure"] += 1
            elif val == "error":
                counts["error"] += 1
            else:
                counts["undetermined"] += 1
    return counts


def _compute_agreement(path_a: Path, path_b: Path) -> float:
    if not path_a.exists() or not path_b.exists():
        return 0.0
    scores_b: dict[str, str] = {}
    with open(path_b, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scores_b[row["conversation_id"]] = row.get("score_value", "undetermined")

    agreeing = 0
    total = 0
    with open(path_a, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row["conversation_id"]
            if cid in scores_b:
                total += 1
                if row.get("score_value") == scores_b[cid]:
                    agreeing += 1

    return round(agreeing / total * 100, 2) if total else 0.0


def _write_summary(run_dir: str, models: list[str], responses: list[dict]) -> None:
    claude_path = Path(run_dir) / "scored_claude.csv"
    summary_path = Path(run_dir) / "summary.csv"

    all_counts: dict[str, dict[str, int]] = {}
    for m in models:
        path = Path(run_dir) / f"scored_{m}.csv"
        all_counts[m] = _count_scored(path)

    # pyrit_counts = _count_pyrit_outcomes(responses)
    # all_counts["pyrit"] = pyrit_counts

    all_scorers = models
    fields = ["metric"] + all_scorers

    rows: list[dict] = []
    for label in ["total", "success", "failure", "error", "undetermined"]:
        row: dict[str, str | int | float] = {"metric": label}
        for s in all_scorers:
            row[s] = all_counts[s][label]
        rows.append(row)

    rate_row: dict[str, str | int | float] = {"metric": "success_rate_pct"}
    for s in all_scorers:
        c = all_counts[s]
        rate_row[s] = round(c["success"] / c["total"] * 100, 2) if c["total"] else 0.0
    rows.append(rate_row)

    agreement_row: dict[str, str | int | float] = {"metric": "agreement_with_claude_pct"}
    for s in all_scorers:
        if s == "claude":
            agreement_row[s] = 100.0
        else:
            s_path = Path(run_dir) / f"scored_{s}.csv"
            agreement_row[s] = _compute_agreement(s_path, claude_path)
    rows.append(agreement_row)

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Summary written to {summary_path}")


async def run_scoring(run_dir: str, models: list[str] | None = None) -> None:
    if models is None:
        models = ["self", "bf16", "claude"]

    await initialize_pyrit_async(memory_db_type=IN_MEMORY, initializers=[])  # type: ignore

    pyrit_env = _parse_pyrit_env()
    responses = _load_raw_responses(run_dir)
    print(f"Loaded {len(responses)} responses from {run_dir}")

    proxy_proc = None
    if "claude" in models:
        proxy_proc = _start_litellm_proxy()

    try:
        tasks = [
            _score_responses(responses, m, pyrit_env, run_dir)
            for m in models
        ]
        await asyncio.gather(*tasks)

        print("\nWriting summary...")
        _write_summary(run_dir, models, responses)

    finally:
        if proxy_proc is not None:
            proxy_proc.terminate()


def main():
    parser = argparse.ArgumentParser(description="Re-score raw responses with multiple scorer models")
    parser.add_argument("--run-dir", required=True, help="Path to run directory containing raw_responses.csv")
    parser.add_argument("--models", default="self,bf16,claude", help="Comma-separated list: self,bf16,claude")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    asyncio.run(run_scoring(args.run_dir, models))


if __name__ == "__main__":
    main()
