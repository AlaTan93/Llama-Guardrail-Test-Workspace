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
    return _original_remove_markdown_json(sanitized)


pyrit.exceptions.exceptions_helpers.remove_markdown_json = _patched_remove_markdown_json
pyrit.exceptions.remove_markdown_json = _patched_remove_markdown_json
