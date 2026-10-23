from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Status = Literal['CREATED','PLANNING','SEARCHING','BROWSING','EXTRACTING','VERIFYING','REPORTING','COMPLETED','PARTIAL','FAILED','CANCELLED']
Verdict = Literal['SUPPORTED','REFUTED','MISLEADING','CONFLICTED','INSUFFICIENT']
TERMINAL = {'COMPLETED','PARTIAL','FAILED','CANCELLED'}

class CreateInvestigation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=3, max_length=2000)
    mode: Literal['quick','deep'] = 'quick'
    data_mode: Literal['live','fixture'] = 'live'

class Plan(BaseModel):
    claims: list[str] = Field(min_length=1, max_length=5)
    queries: list[str] = Field(min_length=1, max_length=2)

class Assessment(BaseModel):
    claim_id: str
    verdict: Verdict
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(max_length=2000)

class Assessments(BaseModel):
    assessments: list[Assessment] = Field(max_length=5)

class Quote(BaseModel):
    claim_id: str
    quote: str = Field(min_length=10, max_length=2000)
    stance: Literal['supports','refutes','context']

class Quotes(BaseModel):
    quotes: list[Quote] = Field(default_factory=list, max_length=8)
