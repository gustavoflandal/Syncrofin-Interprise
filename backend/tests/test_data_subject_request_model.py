"""The data_subject_requests table: columns, cascade on user deletion, protocol format."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_subject_request import DataSubjectRequest, generate_protocol
from app.models.user import User


class TestTheModel:
    pytestmark = pytest.mark.asyncio

    async def test_it_saves_and_reads_back(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(),
            protocol=generate_protocol(),
            user_id=test_user.id,
            kind="access",
            status="resolved_auto",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        assert row.due_at > row.created_at
        assert row.protocol.startswith("DSR-")

    async def test_it_rejects_an_unknown_kind(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(), protocol=generate_protocol(), user_id=test_user.id,
            kind="not-a-kind", status="resolved_auto",
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_deleting_the_user_cascades(self, session: AsyncSession, test_user: User, clean_db):
        row = DataSubjectRequest(
            id=uuid.uuid4(), protocol=generate_protocol(), user_id=test_user.id,
            kind="access", status="resolved_auto",
        )
        session.add(row)
        await session.commit()
        await session.delete(test_user)
        await session.commit()
        remaining = (await session.execute(select(DataSubjectRequest).where(DataSubjectRequest.id == row.id))).scalar_one_or_none()
        assert remaining is None


class TestProtocol:
    def test_it_has_the_year_and_is_unique_across_calls(self):
        import datetime
        first = generate_protocol()
        second = generate_protocol()
        assert first != second
        assert str(datetime.datetime.now().year) in first
