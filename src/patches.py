import re

import pyrit.exceptions
import pyrit.exceptions.exceptions_helpers

_INVALID_JSON_ESCAPE_RE = re.compile(r'\\([^"\\/bfnrtu])')

_original_remove_markdown_json = pyrit.exceptions.exceptions_helpers.remove_markdown_json


def _patched_remove_markdown_json(response_msg: str) -> str:
    sanitized = _INVALID_JSON_ESCAPE_RE.sub(r"\1", response_msg)
    return _original_remove_markdown_json(sanitized)


pyrit.exceptions.exceptions_helpers.remove_markdown_json = _patched_remove_markdown_json
pyrit.exceptions.remove_markdown_json = _patched_remove_markdown_json
