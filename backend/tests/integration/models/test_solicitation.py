from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.chat_session import ChatSession
from api.models.solicitation import (
    Solicitation,
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from api.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_solicitation_persists_with_triage_session_without_owner(
    db_session: AsyncSession,
) -> None:
    user_id, private_session_id, triage_session_id = uuid4(), uuid4(), uuid4()
    user = User(
        id=user_id,
        email="owner@example.com",
        password_hash="hash",
    )
    private_session = ChatSession(
        id=private_session_id,
        user_id=user_id,
        title="Conversa privada",
    )
    triage_session = ChatSession(
        id=triage_session_id,
        user_id=None,
        title="Triagem",
    )
    solicitation = Solicitation(
        summary="Oferta de queijo coalho.",
        request_type=SolicitationType.OFFER,
        urgency=SolicitationUrgency.URGENT,
        session_id=triage_session_id,
    )

    db_session.add(user)
    await db_session.flush()
    db_session.add_all([private_session, triage_session, solicitation])
    await db_session.flush()

    assert isinstance(solicitation.id, UUID)
    assert private_session.user_id == user_id
    assert triage_session.user_id is None
    assert solicitation.status == SolicitationStatus.RECEIVED
    assert solicitation.request_type == SolicitationType.OFFER
    assert solicitation.urgency == SolicitationUrgency.URGENT
    assert solicitation.session_id == triage_session_id
    assert await db_session.get(Solicitation, solicitation.id) is solicitation
