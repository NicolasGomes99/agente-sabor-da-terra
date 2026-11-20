import asyncio
import logging
import os
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..agents.agent import orchestrate_request
from ..agents.config import get_agent_model
from ..agents.consultation import (
    ConsultationResponse,
    ConsultationSourceItem,
)
from ..agents.schemas import (
    OrchestratorFlow,
    OrchestratorRequest,
)
from ..agents.triage import TriageAnalysis
from ..dependencies import get_current_user
from ..models.user import User


router = APIRouter(
    prefix="/infra",
    tags=["infrastructure"],
)

logger = logging.getLogger(__name__)

CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]

SMOKE_TEST_TIMEOUT_SECONDS = 120
SMOKE_SOURCE_ID = "infra-smoke-test-source"

_smoke_test_lock = asyncio.Lock()


class AgentSmokeTestRequest(BaseModel):
    flow: Literal["triage", "consultation"]
    confirm_inference: Literal[True]


class AgentSmokeTestResponse(BaseModel):
    status: Literal["ok"] = "ok"
    model: str
    flow: Literal["triage", "consultation"]
    agent: str


def smoke_test_enabled() -> bool:
    return (
        os.getenv(
            "INFRA_SMOKE_TEST_ENABLED",
            "false",
        ).strip().lower()
        == "true"
    )


def build_smoke_test_request(
    flow: Literal["triage", "consultation"],
) -> OrchestratorRequest:
    session_id = f"infra-smoke-{uuid4()}"

    if flow == "triage":
        return OrchestratorRequest(
            session_id=session_id,
            flow=OrchestratorFlow.TRIAGE,
            message_text=(
                "Olá, gostaria de solicitar 10 kg de tomate "
                "orgânico para entrega em 25/11/2026. "
                "Obrigado."
            ),
            received_at="2026-11-19",
            sender="Comprador Fictício",
            buyer_name="Empresa Fictícia",
            channel="email",
            source_id=session_id,
            is_new_triage_message=True,
        )

    return OrchestratorRequest(
        session_id=session_id,
        flow=OrchestratorFlow.CONSULTATION,
        message_text=(
            "Qual produto está coberto pelo certificado "
            "orgânico apresentado?"
        ),
        received_at="2026-11-19",
        sources=[
            ConsultationSourceItem(
                source_id=SMOKE_SOURCE_ID,
                document_name="certificado-ficticio.pdf",
                reference_label="CERT-TESTE-001",
                content=(
                    "Certificado orgânico fictício para testes. "
                    "Produto certificado: tomate orgânico. "
                    "Validade: 31/12/2027."
                ),
            )
        ],
    )


@router.post(
    "/smoke-test/agents",
    response_model=AgentSmokeTestResponse,
)
async def smoke_test_agents(
    payload: AgentSmokeTestRequest,
    user: CurrentUser,
) -> AgentSmokeTestResponse:
    if not smoke_test_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    if _smoke_test_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Another agent smoke test is running.",
        )

    async with _smoke_test_lock:
        request = build_smoke_test_request(
            payload.flow
        )

        model = get_agent_model()

        try:
            async with asyncio.timeout(
                SMOKE_TEST_TIMEOUT_SECONDS
            ):
                result = await orchestrate_request(
                    request,
                    model=model,
                )

            if result.selected_flow != payload.flow:
                raise RuntimeError(
                    "Unexpected agent flow."
                )

            if payload.flow == "triage":
                if (
                    result.selected_agent != "triage_agent"
                    or not isinstance(
                        result.result,
                        TriageAnalysis,
                    )
                    or not result.result.summary.strip()
                ):
                    raise RuntimeError(
                        "Invalid triage smoke test response."
                    )

            else:
                if (
                    result.selected_agent != "consultation_agent"
                    or not isinstance(
                        result.result,
                        ConsultationResponse,
                    )
                    or not result.result.answer.strip()
                    or not result.result.has_sufficient_data
                    or SMOKE_SOURCE_ID
                    not in result.result.source_ids
                ):
                    raise RuntimeError(
                        "Invalid consultation smoke test response."
                    )

        except TimeoutError:
            logger.warning(
                "Infrastructure agent smoke test timed out: "
                "flow=%s",
                payload.flow,
            )

            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agent smoke test timed out.",
            ) from None

        except Exception as error:
            logger.error(
                "Infrastructure agent smoke test failed: "
                "flow=%s error_type=%s",
                payload.flow,
                type(error).__name__,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Agent smoke test failed.",
            ) from None

        logger.info(
            "Infrastructure agent smoke test succeeded: "
            "flow=%s agent=%s",
            payload.flow,
            result.selected_agent,
        )

        return AgentSmokeTestResponse(
            model=model,
            flow=result.selected_flow,
            agent=result.selected_agent,
        )