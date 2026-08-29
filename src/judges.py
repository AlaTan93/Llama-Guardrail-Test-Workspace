"""Judge construction: PyRIT scorers built from the registry in ``src.scorers``.

All judge traffic goes through the LiteLLM proxy.  Targets are wrapped in
:class:`SanitizingScorerTarget` so malformed judge JSON is repaired in-flight
instead of failing the score.
"""

from pyrit.models import Message
from pyrit.prompt_target import OpenAIChatTarget, PromptChatTarget
from pyrit.score import (
    RefusalScorerPaths,
    SelfAskRefusalScorer,
    SelfAskTrueFalseScorer,
    TrueFalseQuestionPaths,
)

from src.config import LITELLM_ENDPOINT
from src.json_sanitize import sanitize_json_response
from src.scorers import scorer_spec


class SanitizingScorerTarget(PromptChatTarget):
    """Wraps a chat target, sanitising judge JSON responses in-flight."""

    def __init__(self, target: PromptChatTarget):
        self._target = target

    def __getattr__(self, name):
        return getattr(self._target, name)

    async def send_prompt_async(self, *, message: Message) -> list[Message]:
        response = await self._target.send_prompt_async(message=message)
        for msg in response:
            for piece in msg.message_pieces:
                if piece.converted_value_data_type == "text" and piece.converted_value:
                    piece.converted_value = sanitize_json_response(piece.converted_value)
        return response


def make_scorer_target(scorer_type: str) -> OpenAIChatTarget:
    """LiteLLM-routed chat target for the judge behind *scorer_type*."""
    spec = scorer_spec(scorer_type)
    return OpenAIChatTarget(
        endpoint=LITELLM_ENDPOINT,
        api_key="not-needed",
        model_name=spec["model"],
        temperature=0.1,
    )


def build_scorer(scorer_type: str):
    """Build a PyRIT scorer for *scorer_type*, wrapped in JSON sanitisation."""
    target = SanitizingScorerTarget(make_scorer_target(scorer_type))
    rubric = scorer_spec(scorer_type)["rubric"]

    if rubric == "refusal_strict":
        return SelfAskRefusalScorer(
            chat_target=target,
            refusal_system_prompt_path=RefusalScorerPaths.OBJECTIVE_STRICT,
        )
    elif rubric == "refusal_lenient":
        return SelfAskRefusalScorer(
            chat_target=target,
            refusal_system_prompt_path=RefusalScorerPaths.OBJECTIVE_LENIENT,
        )

    return SelfAskTrueFalseScorer(
        chat_target=target,
        true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
    )
