import json
import re

import pyrit.exceptions
import pyrit.exceptions.exceptions_helpers

_INVALID_JSON_ESCAPE_RE = re.compile(r'\\([^"\\/bfnrtu])')

_original_remove_markdown_json = pyrit.exceptions.exceptions_helpers.remove_markdown_json


_SCORE_VALUE_TRUE_RE = re.compile(r'"score_value"\s*:\s*"True"')
_SCORE_VALUE_FALSE_RE = re.compile(r'"score_value"\s*:\s*"False"')


def _patched_remove_markdown_json(response_msg: str) -> str:
    sanitized = _INVALID_JSON_ESCAPE_RE.sub(r"\1", response_msg)
    sanitized = _SCORE_VALUE_TRUE_RE.sub('"score_value": "true"', sanitized)
    sanitized = _SCORE_VALUE_FALSE_RE.sub('"score_value": "false"', sanitized)
    result = _original_remove_markdown_json(sanitized)

    try:
        json.loads(result)
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    score_match = re.search(r'"score_value"\s*:\s*"(true|false)"', result, re.IGNORECASE)
    if not score_match:
        return result
    score_value = score_match.group(1).lower()

    rationale_match = re.search(r'"rationale"\s*:\s*"', result)
    rationale = ""
    if rationale_match:
        remainder = result[rationale_match.end():]
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


pyrit.exceptions.exceptions_helpers.remove_markdown_json = _patched_remove_markdown_json
pyrit.exceptions.remove_markdown_json = _patched_remove_markdown_json
