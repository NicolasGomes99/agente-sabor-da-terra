from api.agents.triage.schemas import TriageAnalysis
from api.helpers.triage import format_triage_analysis


def test_format_triage_analysis_preserves_each_deadline_action() -> None:
    analysis = TriageAnalysis.model_validate(
        {
            "summary": "Oferta com retorno e documentos para inspeção.",
            "request_type": "oferta",
            "urgency": "normal",
            "urgency_reason": "Sem prazo urgente.",
            "received_date_reference": "2026-10-30",
            "extracted_data": {
                "deadlines": [
                    {
                        "action": "resposta",
                        "date_start": "2026-10-31",
                        "reference_raw": "até amanhã",
                    },
                    {
                        "action": "disponibilizacao_de_documentos",
                        "date_start": "2026-11-11",
                        "reference_raw": "no primeiro dia da inspeção",
                    },
                ],
            },
        }
    )

    formatted = format_triage_analysis(analysis)

    assert "Ação: Responder\nPrazo: 31/10/2026" in formatted
    assert (
        "Ação: Disponibilizar documentos\nPrazo: 11/11/2026" in formatted
    )
    assert "Ação: Entregar" not in formatted
    assert "Referência original do prazo: até amanhã" in formatted
    assert (
        "Referência original do prazo: no primeiro dia da inspeção"
        in formatted
    )
    assert analysis.extracted_data.response_deadline == "2026-10-31"
    assert analysis.extracted_data.delivery_date_start is None
