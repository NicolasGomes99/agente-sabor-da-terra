import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.agents.agent import orchestrate_request
from api.agents.schemas import OrchestratorRequest
from api.agents.triage.schemas import TriageAnalysis, TriageInput
from api.database import get_engine, get_session_maker
from api.dependencies import get_document_source_provider
from api.repositories.solicitation import SolicitationRepository
from api.schemas.agent_integration import DocumentRetrievalContext
from api.schemas.solicitation import SolicitationCreate
from api.services.solicitation import SolicitationService

DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "pedidos.json"
)

DEFAULT_IDS = ["PED-2026-001", "PED-2026-003"]


async def run(selected_ids: list[str]) -> None:
    pedidos = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    pedidos_by_id = {pedido["id"]: pedido for pedido in pedidos}

    unknown_ids = set(selected_ids) - pedidos_by_id.keys()

    if unknown_ids:
        raise ValueError(
            f"Pedidos inexistentes: {', '.join(sorted(unknown_ids))}"
        )

    try:
        async with get_session_maker()() as session:
            repository = SolicitationRepository(session)
            service = SolicitationService(repository)
            source_provider = get_document_source_provider(session)

            for pedido_id in dict.fromkeys(selected_ids):
                pedido = pedidos_by_id[pedido_id]

                solicitation_id = uuid5(
                    NAMESPACE_URL,
                    f"facepe:{pedido_id}",
                )

                existing = await repository.get_by_id(solicitation_id)

                if existing is not None:
                    print(f"{pedido_id}: já processado.")
                    continue

                payload = TriageInput(
                    message_text=pedido["mensagem_original"],
                    received_at=pedido["data_recebimento"],
                    sender=pedido["remetente"],
                    buyer_name=pedido["comprador"],
                    channel=pedido["canal"],
                    source_id=pedido_id,
                )

                print(f"Processando {pedido_id}...", flush=True)

                retrieved = await source_provider.retrieve_sources(
                    DocumentRetrievalContext(
                        session_id=solicitation_id,
                        query_text=payload.message_text,
                        flow="triage",
                        reference_date=payload.received_date,
                    )
                )

                response = await orchestrate_request(
                    OrchestratorRequest(
                        session_id=str(solicitation_id),
                        flow="triage",
                        is_new_triage_message=True,
                        sources=retrieved.sources,
                        **payload.model_dump(
                            exclude={"conversation_history"}
                        ),
                    )
                )

                if not isinstance(response.result, TriageAnalysis):
                    raise RuntimeError(
                        f"Resultado de triagem inválido: {pedido_id}"
                    )

                solicitation = await service.create_from_analysis(
                    SolicitationCreate(
                        id=solicitation_id,
                        input=payload,
                        analysis=response.result,
                    )
                )

                print(
                    f"{pedido_id}: solicitação {solicitation.id} criada.",
                    flush=True,
                )

    finally:
        await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Processa mensagens da Facepe e cria cartões de triagem."
    )

    parser.add_argument(
        "ids",
        nargs="*",
        default=DEFAULT_IDS,
        help="Identificadores dos pedidos da Facepe.",
    )

    args = parser.parse_args()

    asyncio.run(run(args.ids or DEFAULT_IDS))


if __name__ == "__main__":
    main()