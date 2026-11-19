from datetime import UTC, date, datetime

from .config import to_pernambuco_date
from .schemas import ConversationTurn, OrchestratorRequest

_NEW_TRIAGE_MESSAGE_MARKERS: tuple[str, ...] = (
    "analise esta mensagem",
    "analise esta nova mensagem",
    "analisar esta mensagem",
    "analise a mensagem",
    "analisar mensagem",
    "analise o pedido",
    "analisar pedido",
    "analise outro pedido",
    "analise outra mensagem",
    "nova mensagem",
    "outro pedido",
    "triar esta mensagem",
    "triar nova mensagem",
    "mensagem recebida",
)


def format_history_context(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    lines = ["<historico_sessao_atual>"]
    for idx, turn in enumerate(history, start=1):
        author = "funcionario" if turn.role == "user" else "assistente"
        flow_attr = f' fluxo="{turn.flow}"' if turn.flow else ""
        date_attr = ""
        if turn.received_at is not None:
            try:
                iso_date = to_pernambuco_date(turn.received_at).isoformat()
                date_attr = f' data_recebimento="{iso_date}"'
            except (TypeError, ValueError):
                date_attr = ""
        source_attr = f' id_origem="{turn.source_id}"' if turn.source_id else ""
        lines.append(
            f'<turno ordem="{idx}" autor="{author}"{flow_attr}{date_attr}{source_attr}>'
        )
        lines.append(turn.content)
        lines.append("</turno>")
    lines.append("</historico_sessao_atual>")
    return "\n".join(lines)


def _find_latest_triage_turn(
    history: list[ConversationTurn],
) -> ConversationTurn | None:
    for turn in reversed(history):
        if turn.received_at is not None and turn.flow in {None, "triage"}:
            return turn
    return None


def is_new_triage_analysis(
    request: OrchestratorRequest,
    prior_history: list[ConversationTurn],
    active_source_id: str | None,
    active_received_at: datetime | date | str | None,
) -> bool:
    """Distingue continuação de triagem existente da análise de uma nova mensagem na mesma sessão."""
    if request.is_new_triage_message is not None:
        return request.is_new_triage_message

    has_prior_triage = active_received_at is not None or any(
        turn.flow == "triage" for turn in prior_history
    )
    if not has_prior_triage:
        return True

    if (
        request.source_id is not None
        and active_source_id is not None
        and request.source_id != active_source_id
    ):
        return True

    if request.message_received_at is not None:
        if active_received_at is None:
            return True
        if to_pernambuco_date(request.message_received_at) != to_pernambuco_date(
            active_received_at
        ):
            return True

    lowered = request.message_text.lower()
    return any(marker in lowered for marker in _NEW_TRIAGE_MESSAGE_MARKERS)


class OrchestratorSessionStore:
    """Mantém o histórico em memória e a referência temporal ativa da triagem por session_id."""

    def __init__(self) -> None:
        self._history_by_session: dict[str, list[ConversationTurn]] = {}
        self._triage_received_at_by_session: dict[str, datetime | date | str] = {}
        self._triage_source_id_by_session: dict[str, str | None] = {}

    def get_history(self, session_id: str) -> list[ConversationTurn]:
        return list(self._history_by_session.get(session_id, []))

    def seed_history(
        self,
        session_id: str,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        existing = self._history_by_session.get(session_id)
        if not existing and turns:
            self._history_by_session[session_id] = list(turns)
        if session_id not in self._triage_received_at_by_session:
            latest = _find_latest_triage_turn(
                self._history_by_session.get(session_id, [])
            )
            if latest is not None and latest.received_at is not None:
                self._triage_received_at_by_session[session_id] = latest.received_at
                self._triage_source_id_by_session[session_id] = latest.source_id
        return self.get_history(session_id)

    def append_turn(self, session_id: str, turn: ConversationTurn) -> None:
        turns = self._history_by_session.setdefault(session_id, [])
        turns.append(turn)
        if turn.flow == "triage" and turn.received_at is not None:
            self._triage_received_at_by_session[session_id] = turn.received_at
            self._triage_source_id_by_session[session_id] = turn.source_id

    def resolve_triage_received_at(
        self,
        request: OrchestratorRequest,
        prior_history: list[ConversationTurn] | None = None,
    ) -> tuple[datetime | date | str, bool]:
        """Resolve a data de recebimento da mensagem em análise e indica se é uma nova análise."""
        history = prior_history if prior_history is not None else self.get_history(request.session_id)
        active_received_at = self._triage_received_at_by_session.get(request.session_id)
        active_source_id = self._triage_source_id_by_session.get(request.session_id)

        if active_received_at is None:
            latest = _find_latest_triage_turn(history)
            if latest is not None and latest.received_at is not None:
                active_received_at = latest.received_at
                active_source_id = latest.source_id

        starts_new = is_new_triage_analysis(
            request=request,
            prior_history=history,
            active_source_id=active_source_id,
            active_received_at=active_received_at,
        )

        if starts_new:
            resolved: datetime | date | str = (
                request.message_received_at
                if request.message_received_at is not None
                else (
                    request.received_at
                    if request.received_at is not None
                    else datetime.now(UTC)
                )
            )
            self._triage_received_at_by_session[request.session_id] = resolved
            self._triage_source_id_by_session[request.session_id] = request.source_id
            return resolved, True

        preserved = (
            active_received_at
            if active_received_at is not None
            else (
                request.message_received_at
                or request.received_at
                or datetime.now(UTC)
            )
        )
        self._triage_received_at_by_session[request.session_id] = preserved
        return preserved, False
