"""DisputeService — ownership scoping, dual-id lookup, and terminal-only
resolved_at (what makes 'awaiting you' distinguishable from 'rejected')."""
import uuid
from contextlib import asynccontextmanager

import pytest

from src.core.disputes import DisputeService
from src.domain.core.constants.statuses import DisputeStatus
from src.domain.exceptions import NotFoundError

SELLER = uuid.uuid4()
OTHER = uuid.uuid4()


class FakeUow:
    def __call__(self):
        @asynccontextmanager
        async def _cm():
            yield self
        return _cm()


class FakeRepo:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}
        self.updates = []

    async def get(self, dispute_id):
        return self.rows.get(dispute_id)

    async def get_by_paypal_id(self, paypal_dispute_id):
        return next((r for r in self.rows.values() if r["paypal_dispute_id"] == paypal_dispute_id), None)

    async def update(self, dispute_id, fields):
        self.updates.append((dispute_id, fields))
        self.rows[dispute_id].update(fields)
        return self.rows[dispute_id]


def _row(did, paypal, seller):
    return {"id": did, "paypal_dispute_id": paypal, "seller_id": seller, "status": "escalated"}


def _svc(rows):
    return DisputeService(disputes=FakeRepo(rows), uow=FakeUow())


async def test_get_owned_ok():
    did = uuid.uuid4()
    svc = _svc([_row(did, "FIXTURE-NR-001", SELLER)])
    d = await svc.get(did, seller_id=SELLER)
    assert d["id"] == did


async def test_get_not_owned_is_404():
    did = uuid.uuid4()
    svc = _svc([_row(did, "FIXTURE-NR-001", OTHER)])
    with pytest.raises(NotFoundError):
        await svc.get(did, seller_id=SELLER)


async def test_get_missing_is_404():
    svc = _svc([])
    with pytest.raises(NotFoundError):
        await svc.get(uuid.uuid4(), seller_id=SELLER)


async def test_get_by_any_id_resolves_uuid_and_paypal():
    did = uuid.uuid4()
    svc = _svc([_row(did, "FIXTURE-NR-001", SELLER)])
    by_uuid = await svc.get_by_any_id(str(did), seller_id=SELLER)
    by_paypal = await svc.get_by_any_id("FIXTURE-NR-001", seller_id=SELLER)
    assert by_uuid["id"] == did == by_paypal["id"]


async def test_set_status_terminal_stamps_resolved_at():
    did = uuid.uuid4()
    repo = FakeRepo([_row(did, "FIXTURE-NR-001", SELLER)])
    svc = DisputeService(disputes=repo, uow=FakeUow())
    await svc.set_status(did, status=DisputeStatus.RESOLVED.value, outcome="refund")
    _, fields = repo.updates[-1]
    assert fields["resolved_at"] is not None


async def test_set_status_escalated_leaves_resolved_at_none():
    did = uuid.uuid4()
    repo = FakeRepo([_row(did, "FIXTURE-NR-001", SELLER)])
    svc = DisputeService(disputes=repo, uow=FakeUow())
    await svc.set_status(did, status=DisputeStatus.ESCALATED.value)
    _, fields = repo.updates[-1]
    assert fields["resolved_at"] is None


async def test_set_status_rejected_stamps_resolved_at():
    did = uuid.uuid4()
    repo = FakeRepo([_row(did, "FIXTURE-NR-001", SELLER)])
    svc = DisputeService(disputes=repo, uow=FakeUow())
    await svc.set_status(did, status=DisputeStatus.REJECTED.value)
    _, fields = repo.updates[-1]
    assert fields["resolved_at"] is not None
