from datetime import UTC, date, datetime

from .config import to_pernambuco_date
from .schemas import ConversationTurn
from .triage import TriageAnalysis


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
        lines.append(f'<turno ordem="{idx}" autor="{author}"{flow_attr}{date_attr}>')
        lines.append(turn.content)
        lines.append("</turno>")
    lines.append("</historico_sessao_atual>")
    return "\n".join(lines)


class OrchestratorSessionStore:
    """Mantém o histórico em memória e metadados da triagem isolados por session_id."""

    def __init__(self) -> None:
        self._history_by_session: dict[str, list[ConversationTurn]] = {}
        self._triage_received_at_by_session: dict[str, datetime | date | str] = {}
        self._last_triage_analysis_by_session: dict[str, TriageAnalysis] = {}

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
            for turn in self._history_by_session.get(session_id, []):
                if turn.received_at is not None and turn.flow in {None, "triage"}:
                    self._triage_received_at_by_session[session_id] = turn.received_at
                    break
        return self.get_history(session_id)

    def append_turn(self, session_id: str, turn: ConversationTurn) -> None:
        turns = self._history_by_session.setdefault(session_id, [])
        turns.append(turn)
        if (
            turn.flow == "triage"
            and turn.received_at is not None
            and session_id not in self._triage_received_at_by_session
        ):
            self._triage_received_at_by_session[session_id] = turn.received_at

    def resolve_triage_received_at(
        self,
        session_id: str,
        request_received_at: datetime | date | str | None,
        history: list[ConversationTurn] | None = None,
    ) -> datetime | date | str:
        """Retorna a data de recebimento associada à mensagem em análise na sessão."""
        if session_id in self._triage_received_at_by_session:
            return self._triage_received_at_by_session[session_id]

        for turn in history or []:
            if turn.received_at is not None and turn.flow in {None, "triage"}:
                self._triage_received_at_by_session[session_id] = turn.received_at
                return turn.received_at

        resolved: datetime | date | str = (
            request_received_at if request_received_at is not None else datetime.now(UTC)
        )
        self._triage_received_at_by_session[session_id] = resolved
        return resolved

    def get_last_triage_analysis(self, session_id: str) -> TriageAnalysis | None:
        return self._last_triage_analysis_by_session.get(session_id)

    def set_last_triage_analysis(
        self,
        session_id: str,
        analysis: TriageAnalysis,
    ) -> None:
        self._last_triage_analysis_by_session[session_id] = analysis
