import { Badge } from "@/components/ui/badge";
import type {
  DocumentStatus,
  FieldStatus,
  Outcome,
  OverallStatus,
  Severity,
} from "@/services/types";

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  if (value >= 0.9) return <Badge variant="success">{pct}%</Badge>;
  if (value >= 0.7) return <Badge variant="info">{pct}%</Badge>;
  if (value >= 0.4) return <Badge variant="warning">{pct}%</Badge>;
  return <Badge variant="danger">{pct}%</Badge>;
}

export function FieldStatusBadge({ status }: { status: FieldStatus }) {
  if (status === "match") return <Badge variant="success">match</Badge>;
  if (status === "mismatch") return <Badge variant="danger">mismatch</Badge>;
  return <Badge variant="warning">uncertain</Badge>;
}

export function OverallStatusBadge({ status }: { status: OverallStatus }) {
  if (status === "all_match") return <Badge variant="success">all match</Badge>;
  if (status === "has_uncertain") return <Badge variant="warning">has uncertain</Badge>;
  return <Badge variant="danger">has mismatch</Badge>;
}

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  if (outcome === "auto_approve") return <Badge variant="success">auto-approve</Badge>;
  if (outcome === "human_review") return <Badge variant="warning">human review</Badge>;
  return <Badge variant="danger">draft amendment</Badge>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  if (severity === "critical") return <Badge variant="danger">critical</Badge>;
  if (severity === "major") return <Badge variant="warning">major</Badge>;
  return <Badge variant="secondary">minor</Badge>;
}

const DOC_STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "uploaded",
  preprocessing: "preprocessing",
  extracting: "extracting",
  validating: "validating",
  deciding: "deciding",
  completed: "completed",
  failed: "failed",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const label = DOC_STATUS_LABEL[status] ?? status;
  if (status === "completed") return <Badge variant="success">{label}</Badge>;
  if (status === "failed") return <Badge variant="danger">{label}</Badge>;
  return <Badge variant="info">{label}</Badge>;
}
