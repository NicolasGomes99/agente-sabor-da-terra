from typing import Literal

from pydantic import BaseModel, Field

FindingKind = Literal[
    "exigencia",
    "certificacao",
    "sazonalidade",
    "capacidade_estimada",
    "historico",
    "divergencia",
    "pendencia",
]


class TriageDocumentFinding(BaseModel):
    kind: FindingKind
    description: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    needs_follow_up: bool = False


class TriageDocumentEnrichment(BaseModel):
    findings: list[TriageDocumentFinding] = Field(default_factory=list)

    @property
    def source_ids(self) -> list[str]:
        return list(
            dict.fromkeys(
                source_id
                for finding in self.findings
                for source_id in finding.source_ids
            )
        )
