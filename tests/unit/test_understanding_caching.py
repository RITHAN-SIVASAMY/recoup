"""Perf regression guard: `classify()`/`score_uplift()`/`score_propensity()`
each read a small `metrics.json` for their `model_version`, and `classify()`
additionally builds a `shap.TreeExplainer` over the classifier's full tree
ensemble. None of these change within a process, so all four must be
memoized the same way `understanding.artifacts._load()` already memoizes
the model files themselves -- rebuilding the SHAP explainer per call alone
turned a 500-case `make demo` batch from ~1 minute into ~10 minutes before
this was caught (see docs/09-INCIDENT-LOG.md).
"""

from __future__ import annotations

import pytest

from recoup.understanding.classify import _classifier_explainer, _classifier_model_version
from recoup.understanding.propensity import _model_version as propensity_model_version
from recoup.understanding.uplift import _model_version as uplift_model_version

pytestmark = pytest.mark.unit


def test_classifier_model_version_is_memoized() -> None:
    first = _classifier_model_version()
    hits_before = _classifier_model_version.cache_info().hits
    second = _classifier_model_version()
    assert first == second
    assert _classifier_model_version.cache_info().hits == hits_before + 1


def test_classifier_explainer_is_built_exactly_once_and_reused() -> None:
    first = _classifier_explainer()
    hits_before = _classifier_explainer.cache_info().hits
    second = _classifier_explainer()
    assert first is second  # the same object, not a fresh TreeExplainer
    assert _classifier_explainer.cache_info().hits == hits_before + 1


def test_uplift_model_version_is_memoized() -> None:
    first = uplift_model_version()
    hits_before = uplift_model_version.cache_info().hits
    second = uplift_model_version()
    assert first == second
    assert uplift_model_version.cache_info().hits == hits_before + 1


@pytest.mark.parametrize("arm", ["baseline", "treated"])
def test_propensity_model_version_is_memoized_per_arm(arm: str) -> None:
    first = propensity_model_version(arm)
    hits_before = propensity_model_version.cache_info().hits
    second = propensity_model_version(arm)
    assert first == second
    assert propensity_model_version.cache_info().hits == hits_before + 1
