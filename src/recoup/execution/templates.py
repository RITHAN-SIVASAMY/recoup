"""REG-COMM-04: message templates are loaded from `policies/templates/*.yaml`
as data, not embedded in Python — and every template here is `category:
transactional` on purpose. A promotional template class would need its own,
separate, non-recovery file; `category_for` is written so a template that
isn't `transactional` fails loudly the moment it's used, rather than quietly
letting a promotional message onto a recovery channel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from recoup.domain.models import ActionType

DEFAULT_TEMPLATES_PATH = Path("policies/templates/recovery.yaml")
_ALLOWED_CATEGORY = "transactional"


class MessageTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    sender_identity: str
    opt_out_affordance: str
    max_length: int


class TemplateSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    templates: dict[str, MessageTemplate]


def _read_yaml(path: Path) -> dict[str, Any]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} did not parse to a YAML mapping")
    return raw


class TemplateLoader:
    def __init__(self, path: Path = DEFAULT_TEMPLATES_PATH) -> None:
        self._path = path
        self._cached: TemplateSet | None = None
        self._cached_mtime: float | None = None

    def load(self) -> TemplateSet:
        mtime = self._path.stat().st_mtime
        if self._cached is not None and mtime == self._cached_mtime:
            return self._cached
        template_set = TemplateSet.model_validate(_read_yaml(self._path))
        self._cached = template_set
        self._cached_mtime = mtime
        return template_set


def template_for(action_type: ActionType, templates: TemplateSet) -> MessageTemplate:
    template = templates.templates.get(action_type)
    if template is None:
        raise ValueError(f"no template defined for action_type {action_type!r}")
    if template.category != _ALLOWED_CATEGORY:
        raise ValueError(
            f"template for {action_type!r} is category {template.category!r}, "
            f"not {_ALLOWED_CATEGORY!r} — REG-COMM-04 forbids promotional content on a recovery channel"
        )
    return template
