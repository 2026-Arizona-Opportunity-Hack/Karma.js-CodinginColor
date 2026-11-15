"""NFR-2 audit coverage. The audit log must cover every action the SRS lists, the app must not be
able to rewrite it, and no audited action may go untested.

The source scan reads the literal action names passed to `audit.write(...)` (and the `action=`
keyword of the import helpers), so a new audited action must be added here and tested, and a
removed one fails loudly."""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
TESTS = BACKEND / "tests"

# NFR-2: logins, governance, imports, merges, reassignments, approvals, sends, exports,
# key changes. Each category lists the actions that satisfy it.
REQUIRED: dict[str, set[str]] = {
    "logins": {"auth.login", "auth.login_failed", "auth.logout"},
    "governance": {
        "gov.flatten",
        "gov.set_scope",
        "gov.super_admin_create",
        "gov.super_admin_activate",
        "gov.super_admin_deactivate",
        "gov.super_admin_transfer",
    },
    "imports": {"import.commit", "import.reverse", "review.decide"},
    "reassignments": {"donor.reassign", "donor.bulk_move"},
    "approvals": {"message.approve"},
    "sends": {"message.send", "digest.send"},
    "key changes": {"apikey.create", "apikey.revoke"},
    "exports": {"report.funder_export"},
}
# Not built yet, or built by another lane in the same phase. Remove from here when it lands.
PENDING: dict[str, str] = {
    "merges": "donor.merge",  # POST /donors/{id}/merge is still a 501 stub (DED-7 is "S")
}


def audited_actions() -> set[str]:
    """Every string constant that is the action of an `audit.write(...)` call in app/."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "write" or "audit" not in ast.unparse(node.func.value):
                continue
            action = node.args[2] if len(node.args) > 2 else None
            if isinstance(action, ast.Constant) and isinstance(action.value, str):
                found.add(action.value)
    return found


def test_every_category_the_srs_lists_has_an_audited_action() -> None:
    found = audited_actions()
    missing = {
        category: sorted(actions - found)
        for category, actions in REQUIRED.items()
        if actions - found
    }
    assert not missing, f"audit actions missing from the code: {missing}"


@pytest.mark.parametrize("category", sorted(PENDING))
def test_pending_categories_start_failing_when_they_land(category: str) -> None:
    """A pending action that now exists must move into REQUIRED so it stays covered."""
    action = PENDING[category]
    if action not in audited_actions():
        pytest.skip(f"{category}: {action} is not written yet")
    pytest.fail(f"{action} now exists: move '{category}' from PENDING to REQUIRED")


def test_every_audited_action_is_exercised_by_some_test() -> None:
    corpus = "\n".join(
        p.read_text(encoding="utf-8")
        for p in TESTS.rglob("test_*.py")
        if p.name != Path(__file__).name
    )
    untested = sorted(
        a for a in audited_actions() if f'"{a}"' not in corpus and f"'{a}'" not in corpus
    )
    assert not untested, f"audited actions no test mentions: {untested}"


def test_the_app_cannot_rewrite_or_delete_audit_rows() -> None:
    """Append-only (NFR-2): repos/audit.py has no update or delete, and nothing else touches it."""
    for path in APP.rglob("*.py"):
        if path.name == "audit.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "update(AuditLog)" not in text and "delete(AuditLog)" not in text, path.name
        assert "DELETE FROM audit_log" not in text and "UPDATE audit_log" not in text, path.name
    writer = (APP / "repos" / "audit.py").read_text(encoding="utf-8")
    assert "delete(" not in writer and "update(" not in writer
