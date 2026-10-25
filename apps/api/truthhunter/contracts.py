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
    workflow: Literal['investigation','search'] = 'investigation'

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
    publisher: str = Field(default='',max_length=300)
    origin_kind: Literal['primary','secondary','unknown'] = 'unknown'
    attribution_quote: str = Field(default='',max_length=1500)
    origin_url: str = Field(default='',max_length=2000)
    provenance_reason: str = Field(default='',max_length=2000)

class SourceSelection(BaseModel):
    source_ids: list[str] = Field(min_length=1,max_length=6)
    rationale: str = Field(max_length=2000)

class ImageInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data_url: str = Field(max_length=7_000_000)

class ImageText(BaseModel):
    text: str = Field(min_length=3,max_length=2000)

class SourceProfile(BaseModel):
    source_id: str
    publisher: str = Field(max_length=300)
    origin_kind: Literal['primary','secondary','unknown']
    attribution_quote: str = Field(default='',max_length=1500)
    origin_url: str = Field(default='',max_length=2000)
    rationale: str = Field(max_length=2000)

class SourceProfiles(BaseModel):
    sources: list[SourceProfile] = Field(default_factory=list,max_length=6)

class SourceReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_id: str
    origin_group: str = Field(min_length=1,max_length=150)
    role: Literal['primary','original_reporting','attributed','unknown']
    independence_confirmed: bool = False
    basis_quote: str = Field(min_length=10,max_length=1500)
    reason: str = Field(min_length=20,max_length=2000)

class EvidenceReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    evidence_id: str
    stance: Literal['supports','refutes','context']
    relevant: bool
    time_matches: bool
    reason: str = Field(min_length=10,max_length=1000)

class ClaimReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    claim_id: str
    method: Literal['independent_sources','primary_document','insufficient']
    documentary_scope: str = Field(default='',max_length=2000)
    rationale: str = Field(min_length=20,max_length=2000)

class ReviewSubmission(BaseModel):
    model_config=ConfigDict(extra='forbid')
    report_id: str
    reviewer: str = Field(min_length=2,max_length=100)
    review_type: Literal['manual','assistant']
    acknowledged: bool
    sources: list[SourceReview] = Field(default_factory=list,max_length=6)
    evidence: list[EvidenceReview] = Field(default_factory=list,max_length=48)
    claims: list[ClaimReview] = Field(min_length=1,max_length=5)
