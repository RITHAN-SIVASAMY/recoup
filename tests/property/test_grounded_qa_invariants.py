"""FR-14.5/CON-04: no combination of declared citations, inline citations,
and retrieved event IDs can make `citations_are_valid` accept an answer
that cites something outside the retrieved set, or that disagrees with
itself between its two citation surfaces. This is the property behind the
hallucination guard in `audit/qa.py::ask` — proven here without a database,
independently of any single hand-picked example.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.audit.qa import citations_are_valid

pytestmark = pytest.mark.property

_ids = st.sets(st.text(alphabet="ABCDEFGH01234567", min_size=5, max_size=8), max_size=6)


@given(declared=_ids, inline=_ids, valid_ids=_ids)
def test_validity_never_holds_if_declared_cites_something_not_retrieved(
    declared: set[str], inline: set[str], valid_ids: set[str]
) -> None:
    if citations_are_valid(declared, inline, valid_ids):
        assert declared.issubset(valid_ids)


@given(declared=_ids, inline=_ids, valid_ids=_ids)
def test_validity_never_holds_if_the_two_citation_surfaces_disagree(
    declared: set[str], inline: set[str], valid_ids: set[str]
) -> None:
    if citations_are_valid(declared, inline, valid_ids):
        assert declared == inline


@given(valid_ids=_ids)
def test_an_empty_citation_set_is_never_valid_even_if_it_trivially_agrees(
    valid_ids: set[str],
) -> None:
    assert citations_are_valid(set(), set(), valid_ids) is False


@given(shared=_ids)
def test_citations_that_exactly_match_a_subset_of_retrieved_ids_are_valid(
    shared: set[str],
) -> None:
    if not shared:
        return
    assert citations_are_valid(shared, shared, shared) is True
