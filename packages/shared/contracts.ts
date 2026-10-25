// Backend OpenAPI is authoritative. Exported schema: packages/shared/openapi.json.
export type InvestigationStatus='CREATED'|'PLANNING'|'SEARCHING'|'BROWSING'|'EXTRACTING'|'VERIFYING'|'REPORTING'|'COMPLETED'|'PARTIAL'|'FAILED'|'CANCELLED';
export type Verdict='SUPPORTED'|'REFUTED'|'MISLEADING'|'CONFLICTED'|'INSUFFICIENT';
export type InvestigationWorkflow='investigation'|'search';
