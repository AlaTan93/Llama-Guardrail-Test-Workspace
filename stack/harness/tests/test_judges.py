"""Category convention tests — the contract that attributes scores to judges."""

from app.pyrit.judges import ATTACK_SUCCESS_KIND, REFUSAL_KIND, category, parse_category


def test_category_roundtrip():
    for kind in (ATTACK_SUCCESS_KIND, REFUSAL_KIND):
        for alias in ("judge-self", "judge-bf16", "judge-claude"):
            assert parse_category([category(kind, alias)]) == (kind, alias)


def test_parse_accepts_scalar_and_list():
    assert parse_category("refusal::judge-self") == ("refusal", "judge-self")
    assert parse_category(["attack_success::judge-claude"]) == ("attack_success", "judge-claude")


def test_parse_rejects_missing_separator_and_empty():
    assert parse_category(["judge-claude"]) is None
    assert parse_category([]) is None
    assert parse_category(None) is None
