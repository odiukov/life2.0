from datetime import timedelta
from uuid import UUID

import pytest
from kitchen.domain.digest import build_digest
from kitchen.domain.model import Status
from kitchen.testing import TODAY, make_batch


def test_groups_items() -> None:
    expired = make_batch(id=1, expires_on=TODAY - timedelta(days=1))
    today = make_batch(id=2, expires_on=TODAY)
    tomorrow = make_batch(id=3, expires_on=TODAY + timedelta(days=1))
    check = make_batch(id=4, expires_on=TODAY + timedelta(days=5), next_check_on=TODAY)
    fine = make_batch(
        id=5, expires_on=TODAY + timedelta(days=5), next_check_on=TODAY + timedelta(days=4)
    )
    view = build_digest([fine, check, tomorrow, today, expired], TODAY)
    assert [b.id for b in view.expired] == [UUID(int=1)]
    assert [b.id for b in view.expiring] == [UUID(int=2), UUID(int=3)]
    assert [b.id for b in view.to_check] == [UUID(int=4)]
    assert view.hidden == 0
    assert [b.id for b in view.items()] == [UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4)]
    assert not view.is_empty


def test_empty_digest() -> None:
    fine = make_batch(
        id=1, expires_on=TODAY + timedelta(days=5), next_check_on=TODAY + timedelta(days=4)
    )
    assert build_digest([fine], TODAY).is_empty


def test_limit_keeps_most_urgent() -> None:
    expired = [make_batch(id=i, expires_on=TODAY - timedelta(days=1)) for i in range(1, 11)]
    checks = [
        make_batch(id=i, expires_on=TODAY + timedelta(days=9), next_check_on=TODAY)
        for i in range(11, 21)
    ]
    view = build_digest(checks + expired, TODAY, limit=15)
    assert len(view.expired) == 10
    assert len(view.to_check) == 5
    assert view.hidden == 5


def test_digest_ignores_inactive_batches_and_prioritizes_expiry_over_check() -> None:
    expired = make_batch(id=1, expires_on=TODAY - timedelta(days=1), next_check_on=TODAY)
    consumed = make_batch(id=2, expires_on=TODAY, status=Status.CONSUMED)
    discarded = make_batch(id=3, expires_on=TODAY, status=Status.DISCARDED)
    view = build_digest([discarded, consumed, expired], TODAY)
    assert [batch.id for batch in view.expired] == [UUID(int=1)]
    assert view.expiring == ()
    assert view.to_check == ()
    assert view.hidden == 0


def test_zero_limit_hides_all_candidates_without_counting_fine_items() -> None:
    candidate = make_batch(id=1, expires_on=TODAY)
    fine = make_batch(id=2)
    view = build_digest([candidate, fine], TODAY, limit=0)
    assert view.is_empty
    assert view.items() == []
    assert view.hidden == 1


def test_limit_can_stop_in_expiring_group() -> None:
    expired = make_batch(id=3, expires_on=TODAY - timedelta(days=1))
    expiring = make_batch(id=2, expires_on=TODAY)
    tomorrow = make_batch(id=1, expires_on=TODAY + timedelta(days=1))
    check = make_batch(id=4, next_check_on=TODAY)
    view = build_digest([check, tomorrow, expiring, expired], TODAY, limit=2)
    assert [batch.id for batch in view.items()] == [UUID(int=3), UUID(int=2)]
    assert view.to_check == ()
    assert view.hidden == 2


def test_negative_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="limit"):
        build_digest([make_batch(expires_on=TODAY)], TODAY, limit=-1)
