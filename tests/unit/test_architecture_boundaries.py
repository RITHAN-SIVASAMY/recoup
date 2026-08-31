"""EventStore.append must be the only write path for case state: no module outside
`audit/` may import the ORM rows that back the `cases`/`case_events` tables.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src" / "recoup"
_GUARDED_NAMES = {"CaseRow", "CaseEventRow", "Base"}


def _imports_guarded_schema(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("audit.schema")
            and any(alias.name in _GUARDED_NAMES for alias in node.names)
        ):
            return True
    return False


def test_no_module_outside_audit_imports_the_cases_orm() -> None:
    offenders = [
        str(path.relative_to(_SRC))
        for path in _SRC.rglob("*.py")
        if "audit" not in path.relative_to(_SRC).parts and _imports_guarded_schema(path)
    ]
    assert not offenders, f"cases/case_events ORM imported outside audit/: {offenders}"
