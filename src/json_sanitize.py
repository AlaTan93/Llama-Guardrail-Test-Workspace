"""JSON response sanitisation for scorer output.

Both ``patches.py`` (PyRIT monkey-patch for Phase-1 objective scorer) and
``scoring.py`` (Phase-2 LLM judges via ``SanitizingScorerTarget``) need to turn
malformed / loosely-formatted scorer JSON into valid JSON with a normalised
``score_value``.  The shared logic lives here.
"""

import json
import re

_INVALID_JSON_ESCAPE_RE = re.compile(r'\\([^"\\/bfnrtu])')
_SCORE_VALUE_TRUE_RE = re.compile(r'"score_value"\s*:\s*"True"', re.IGNORECASE)
_SCORE_VALUE_FALSE_RE = re.compile(r'"score_value"\s*:\s*"False"', re.IGNORECASE)

_SCORE_VALUE_RE = re.compile(
    r'"score_value"\s*:\s*"(true|false|True|False)"', re.IGNORECASE
)
_RATIONALE_RE = re.compile(r'"rationale"\s*:\s*"')


def _fix_escapes_and_case(text: str) -> str:
    """Normalise invalid JSON escapes and capitalised True/False score values."""
    text = _INVALID_JSON_ESCAPE_RE.sub(r"\1", text)
    text = _SCORE_VALUE_TRUE_RE.sub('"score_value": "true"', text)
    text = _SCORE_VALUE_FALSE_RE.sub('"score_value": "false"', text)
    return text


def _extract_rationale(text: str) -> str:
    """Best-effort extraction of the ``rationale`` field from *text*."""
    match = _RATIONALE_RE.search(text)
    if not match:
        return ""
    remainder = text[match.end():]
    end_match = re.search(r'",\s*"metadata"', remainder)
    if end_match:
        return remainder[:end_match.start()]
    return remainder.rstrip('"}').rstrip('"')


def sanitize_json_response(text: str) -> str:
    """Return valid JSON with ``score_value`` / ``rationale`` keys.

    Tries, in order:
      1. Fix escapes + capitalisation, then ``json.loads``.
      2. Regex-extract ``score_value`` and ``rationale``.
      3. Fallback to ``score_value = "false"`` with empty rationale.
    """
    text = _fix_escapes_and_case(text)

    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    score_match = _SCORE_VALUE_RE.search(text)
    score_value = score_match.group(1).lower() if score_match else "false"
    rationale = _extract_rationale(text)

    return json.dumps({
        "score_value": score_value,
        "description": "",
        "rationale": rationale,
        "metadata": "",
    })
