"""REG-COMM-04/05: templates load as data, are always `transactional`, and
`template_for` refuses anything else rather than silently allowing it.
"""

from __future__ import annotations

from pathlib import Path

import pydantic
import pytest
import yaml

from recoup.execution.templates import MessageTemplate, TemplateLoader, TemplateSet, template_for

pytestmark = pytest.mark.unit

REAL_TEMPLATES_PATH = Path("policies/templates/recovery.yaml")


def test_load_produces_a_valid_template_set_from_the_real_file() -> None:
    templates = TemplateLoader(REAL_TEMPLATES_PATH).load()
    assert "send_message" in templates.templates
    assert templates.templates["send_message"].category == "transactional"


def test_template_for_returns_the_matching_template() -> None:
    templates = TemplateLoader(REAL_TEMPLATES_PATH).load()
    template = template_for("send_message", templates)
    assert template.opt_out_affordance
    assert template.sender_identity


def test_template_for_raises_for_an_action_type_with_no_template() -> None:
    templates = TemplateSet(version=1, templates={})
    with pytest.raises(ValueError, match="no template defined"):
        template_for("send_message", templates)


def test_template_for_refuses_a_non_transactional_template() -> None:
    templates = TemplateSet(
        version=1,
        templates={
            "send_message": MessageTemplate(
                category="promotional",
                sender_identity="Acme",
                opt_out_affordance="Reply STOP",
                max_length=160,
            )
        },
    )
    with pytest.raises(ValueError, match="REG-COMM-04"):
        template_for("send_message", templates)


def test_loading_twice_without_a_file_change_returns_the_cached_set(tmp_path: Path) -> None:
    dest = tmp_path / "recovery.yaml"
    dest.write_text(REAL_TEMPLATES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    loader = TemplateLoader(dest)
    first = loader.load()
    second = loader.load()
    assert first is second


def test_an_invalid_template_file_raises() -> None:
    with pytest.raises(pydantic.ValidationError):
        TemplateSet.model_validate(yaml.safe_load("version: 1\ntemplates:\n  send_message: {}\n"))
