import asyncio
import csv
from io import BytesIO, StringIO
from uuid import uuid4

from sqlalchemy import select

from api.database import get_session_maker
from api.dependencies import get_document_storage
from api.models.chat_message import ChatMessage, ChatMessageRole
from api.models.chat_session import ChatSession
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk
from api.models.user import User

POLICY_FILENAME = "politica-comercial-2026.txt"
LOTES_FILENAME = "lotes.csv"

POLICY_TEXT = (
    "Politica Comercial Sabor da Terra - Safra 2026\n\n"
    "Clausula 4.2: Pedidos confirmados ate as 14h tem prazo maximo de entrega "
    "de 48 horas uteis na regiao metropolitana, com lote minimo de 150 kg."
)
POLICY_EXCERPT = (
    "Cláusula 4.2: Pedidos confirmados até as 14h têm prazo máximo de entrega "
    "de 48 horas úteis na região metropolitana, com lote mínimo de 150 kg."
)

# Cenário de aceitação da issue #12 (US06/US07): os dois lotes pertencem a P004,
# com colheita em setembro de 2026 e entrega prevista para 08/09/2026.
LOTES_CSV = (
    "lote_id,produtor_id,produto,quantidade,unidade,data_colheita,data_entrega_prevista,disponibilidade_conf,pedido_historico\n"
    "LOT-2026-0094,P004,alface,300,unidades,2026-09-06,2026-09-08,sim,PED-2026-SEP-008\n"
    "LOT-2026-0095,P004,coentro,150,maços,2026-09-07,2026-09-08,sim,\n"
)


def build_csv_chunks(document_id, csv_text: str) -> list[DocumentChunk]:
    """Um chunk por linha: record_id = lote_id, record_fields = colunas da linha."""
    chunks = []
    for row in csv.DictReader(StringIO(csv_text)):
        chunks.append(
            DocumentChunk(
                document_id=document_id,
                content="; ".join(f"{key}={value}" for key, value in row.items()),
                record_id=row["lote_id"],
                record_fields=dict(row),
                embedding=None,
            )
        )
    return chunks


def add_exchange(
    session, chat_session_id, position: int, question: str, answer: str
) -> ChatMessage:
    session.add(
        ChatMessage(
            session_id=chat_session_id,
            role=ChatMessageRole.USER,
            content=question,
            position=position,
        )
    )
    answer_message = ChatMessage(
        session_id=chat_session_id,
        role=ChatMessageRole.AGENT,
        content=answer,
        position=position + 1,
    )
    session.add(answer_message)
    return answer_message


async def seed_citation_scenario() -> None:
    storage = get_document_storage()
    session_maker = get_session_maker()

    async with session_maker() as session:
        user = await session.scalar(select(User).limit(1))
        if user is None:
            raise RuntimeError(
                "Nenhum usuário encontrado no banco. Cadastre ou faça login com um usuário antes de rodar o seed."
            )

        already_seeded = await session.scalar(
            select(Document).where(
                Document.original_filename.in_([POLICY_FILENAME, LOTES_FILENAME])
            )
        )
        if already_seeded is not None:
            print("Seed já aplicado (documentos de teste existentes). Nada a fazer.")
            return

        # --- Cenário 1: trecho documental ---
        policy_key = f"seed-{uuid4().hex}"
        storage.save(policy_key, BytesIO(POLICY_TEXT.encode("utf-8")))
        policy = Document(original_filename=POLICY_FILENAME, storage_key=policy_key)
        session.add(policy)
        await session.flush()

        policy_chunk = DocumentChunk(
            document_id=policy.id, content=POLICY_EXCERPT, embedding=None
        )
        session.add(policy_chunk)
        await session.flush()

        policy_chat = ChatSession(
            user_id=user.id, title="Validação de fontes - Política Comercial"
        )
        session.add(policy_chat)
        await session.flush()

        policy_answer = add_exchange(
            session,
            policy_chat.id,
            1,
            "Qual é o prazo de entrega e o lote mínimo para pedidos até 14h?",
            "Pedidos confirmados até as 14h têm prazo máximo de entrega de 48 horas "
            "úteis na região metropolitana, com lote mínimo de 150 kg.",
        )
        await session.flush()
        session.add(Citation(message_id=policy_answer.id, chunk_id=policy_chunk.id))

        # --- Cenário 2: registros de CSV (um chunk por linha) ---
        lotes_key = f"seed-{uuid4().hex}"
        storage.save(lotes_key, BytesIO(LOTES_CSV.encode("utf-8")))
        lotes = Document(original_filename=LOTES_FILENAME, storage_key=lotes_key)
        session.add(lotes)
        await session.flush()

        lote_chunks = {c.record_id: c for c in build_csv_chunks(lotes.id, LOTES_CSV)}
        session.add_all(lote_chunks.values())
        await session.flush()

        lotes_chat = ChatSession(
            user_id=user.id, title="Validação de fontes - Lotes (CSV)"
        )
        session.add(lotes_chat)
        await session.flush()

        answer_0094 = add_exchange(
            session,
            lotes_chat.id,
            1,
            "O que sabemos sobre o lote LOT-2026-0094?",
            "O lote LOT-2026-0094 é do produtor P004: 300 unidades de alface, "
            "colhidas em 06/09/2026, com entrega prevista para 08/09/2026. "
            "Referência do pedido histórico: PED-2026-SEP-008.",
        )
        answer_0095 = add_exchange(
            session,
            lotes_chat.id,
            3,
            "E o lote LOT-2026-0095?",
            "O lote LOT-2026-0095 é do produtor P004: 150 maços de coentro, "
            "colhidos em 07/09/2026, com entrega prevista para 08/09/2026.",
        )
        await session.flush()
        session.add(
            Citation(
                message_id=answer_0094.id,
                chunk_id=lote_chunks["LOT-2026-0094"].id,
            )
        )
        session.add(
            Citation(
                message_id=answer_0095.id,
                chunk_id=lote_chunks["LOT-2026-0095"].id,
            )
        )
        await session.commit()

        print("Cenários de teste criados:")
        print(f"  user_email:        {user.email}")
        print(f"  sessão (política): {policy_chat.id}")
        print(f"  sessão (lotes):    {lotes_chat.id}")
        print(f"  {POLICY_FILENAME}: {policy.id}")
        print(f"  {LOTES_FILENAME}:  {lotes.id}")


if __name__ == "__main__":
    asyncio.run(seed_citation_scenario())