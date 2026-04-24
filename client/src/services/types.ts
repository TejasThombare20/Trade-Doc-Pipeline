// Mirrors app/schemas/* on the backend. Kept small and explicit.

export type DocumentStatus =
  | "uploaded"
  | "preprocessing"
  | "extracting"
  | "validating"
  | "deciding"
  | "completed"
  | "failed";

export type Outcome = "auto_approve" | "human_review" | "draft_amendment";

export type OverallStatus = "all_match" | "has_uncertain" | "has_mismatch";

export type FieldStatus = "match" | "mismatch" | "uncertain";

export type Severity = "critical" | "major" | "minor";

export type StageName =
  | "parsing"
  | "extraction"
  | "validation"
  | "decision";

export type StepStatus = "pending" | "success" | "fail";

export interface TenantOption {
  id: string;
  name: string;
  slug: string;
}

export interface DocumentListItem {
  id: string;
  original_name: string;
  type: "document" | "rule_book";
  doc_type: string | null;
  status: DocumentStatus;
  outcome: Outcome | null;
  is_active: boolean;
  created_at: string;
}

export interface DocumentDetail {
  id: string;
  tenant_id: string;
  session_id: string | null;
  type: "document" | "rule_book";
  original_name: string;
  mime_type: string;
  size_bytes: number;
  doc_type: string | null;
  status: DocumentStatus;
  is_active: boolean;
  created_at: string;
  file_url: string | null;
  extraction: Record<string, unknown> | null;
  validation: Record<string, unknown> | null;
  decision: Record<string, unknown> | null;
  pipeline_status: string | null;
  total_tokens_in: number;
  total_tokens_out: number;
}

export interface TimelineStep {
  id: string;
  step_type: string;
  mode: string;
  status: StepStatus;
  response: Record<string, unknown> | null;
  tokens_in: number | null;
  tokens_out: number | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SSESnapshot {
  event: "snapshot";
  document_id: string;
  document_status: DocumentStatus;
  steps: TimelineStep[];
  pipeline_status: string | null;
  total_tokens_in?: number;
  total_tokens_out?: number;
}

export interface SSEStepEvent {
  event: "step_started" | "step_completed";
  step_type: string;
  mode?: string;
  run_id: string;
  status?: string;
  response?: Record<string, unknown>;
  tokens_in?: number;
  tokens_out?: number;
}

export interface SSESessionEvent {
  event: "session_started" | "session_completed" | "closed";
  type?: string;
  status?: string;
  total_tokens_in?: number;
  total_tokens_out?: number;
  error?: string;
}

export type SSEEvent = SSESnapshot | SSEStepEvent | SSESessionEvent;

export interface UploadResponse {
  document_id: string;
  session_id: string;
  status: string;
}

export interface RuleBookBundle {
  document: {
    id: string;
    tenant_id: string;
    session_id: string | null;
    type: "rule_book";
    original_name: string;
    mime_type: string;
    size_bytes: number;
    doc_type: string | null;
    status: string;
    is_active: boolean;
    created_at: string;
    file_url: string;
  };
  extracted_rules: Record<string, unknown>[] | null;
}

export interface RuleBookUploadResponse {
  document_id: string;
  session_id: string;
  status: string;
}

export interface ExtractedField {
  value: string | null;
  confidence: number;
  source_snippet: string | null;
}

export interface FieldValidation {
  status: FieldStatus;
  found: string | null;
  expected: string | null;
  severity: Severity;
  reasoning: string;
  rule_id?: string | null;
}

export interface Discrepancy {
  field: string;
  found: string | null;
  expected: string | null;
  severity: Severity;
  reasoning: string;
}
