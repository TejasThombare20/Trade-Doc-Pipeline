import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DocumentStatusBadge } from "@/components/StatusBadges";
import { Timeline } from "@/components/Timeline";
import { getDocument } from "@/services/api";
import type { DocumentDetail } from "@/services/types";
import { formatBytes, formatRelative } from "@/lib/utils";

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await getDocument(id);
        if (!cancelled) setDoc(d);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/" className="text-sm text-primary hover:underline flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to documents
        </Link>
        <div className="text-destructive">{error}</div>
      </div>
    );
  }

  if (!doc) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading document…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              {doc.original_name}
            </h1>
            <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
              <span>{formatBytes(doc.size_bytes)}</span>
              <span>·</span>
              <span>{doc.mime_type}</span>
              <span>·</span>
              <span>{formatRelative(doc.created_at)}</span>
              {doc.doc_type && (
                <>
                  <span>·</span>
                  <span className="text-primary">{doc.doc_type.replace(/_/g, " ")}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {doc.file_url && (
            <Button
              variant="outline"
              size="sm"
              asChild
            >
              <a href={doc.file_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-1.5" />
                View document
              </a>
            </Button>
          )}
          <DocumentStatusBadge status={doc.status} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pipeline Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Timeline documentId={doc.id} sessionId={doc.session_id} />
        </CardContent>
      </Card>

      {doc.extraction && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Extraction Output</CardTitle>
          </CardHeader>
          <CardContent>
            <ExtractionView data={doc.extraction} />
          </CardContent>
        </Card>
      )}

      {doc.validation && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Validation Output</CardTitle>
          </CardHeader>
          <CardContent>
            <ValidationView data={doc.validation} />
          </CardContent>
        </Card>
      )}

      {doc.decision && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Decision</CardTitle>
          </CardHeader>
          <CardContent>
            <DecisionView data={doc.decision} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ExtractionView({ data }: { data: Record<string, unknown> }) {
  const fields = data.fields as Record<string, Record<string, unknown>> | undefined;
  if (!fields) {
    return <pre className="text-xs overflow-auto text-muted-foreground">{JSON.stringify(data, null, 2)}</pre>;
  }
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">
        Document type: <span className="font-medium text-foreground">{(data.doc_type as string)?.replace(/_/g, " ")}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b border-border">
              <th className="text-left font-medium py-2 pr-3">Field</th>
              <th className="text-left font-medium py-2 px-3">Value</th>
              <th className="text-left font-medium py-2 px-3">Confidence</th>
              <th className="text-left font-medium py-2 px-3">Source</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(fields).map(([name, f]) => (
              <tr key={name} className="border-b border-border last:border-0">
                <td className="py-2 pr-3 font-medium text-foreground">{name.replace(/_/g, " ")}</td>
                <td className="py-2 px-3 text-foreground">{f.value != null ? (f.value as string) : <span className="text-muted-foreground italic">absent</span>}</td>
                <td className="py-2 px-3">
                  {f.value != null && (
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      (f.confidence as number) >= 0.9 ? "bg-emerald-500/10 text-emerald-500" :
                      (f.confidence as number) >= 0.7 ? "bg-blue-500/10 text-blue-400" :
                      (f.confidence as number) >= 0.4 ? "bg-amber-500/10 text-amber-400" :
                      "bg-destructive/10 text-destructive"
                    }`}>
                      {Math.round((f.confidence as number) * 100)}%
                    </span>
                  )}
                </td>
                <td className="py-2 px-3 text-xs text-muted-foreground max-w-xs truncate">{f.source_snippet as string}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ValidationView({ data }: { data: Record<string, unknown> }) {
  const results = data.results as Record<string, Record<string, unknown>> | undefined;
  if (results === undefined || results === null) {
    return <pre className="text-xs overflow-auto text-muted-foreground">{JSON.stringify(data, null, 2)}</pre>;
  }
  const entries = Object.entries(results);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <span className={`font-medium px-2.5 py-1 rounded-full text-xs ${
          data.overall_status === "all_match" ? "bg-emerald-500/10 text-emerald-500" :
          data.overall_status === "has_uncertain" ? "bg-amber-500/10 text-amber-400" :
          "bg-destructive/10 text-destructive"
        }`}>
          {(data.overall_status as string)?.replace(/_/g, " ")}
        </span>
      </div>
      {data.summary && <div className="text-sm text-muted-foreground">{data.summary as string}</div>}
      {entries.length === 0 ? (
        <div className="text-sm text-muted-foreground italic">No field-level results returned by the validator.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th className="text-left font-medium py-2 pr-3">Field</th>
                <th className="text-left font-medium py-2 px-3">Status</th>
                <th className="text-left font-medium py-2 px-3">Found</th>
                <th className="text-left font-medium py-2 px-3">Expected</th>
                <th className="text-left font-medium py-2 px-3">Severity</th>
                <th className="text-left font-medium py-2 px-3">Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([name, v]) => (
                <tr key={name} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3 font-medium text-foreground">{name.replace(/_/g, " ")}</td>
                  <td className="py-2 px-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      v.status === "match" ? "bg-emerald-500/10 text-emerald-500" :
                      v.status === "mismatch" ? "bg-destructive/10 text-destructive" :
                      "bg-amber-500/10 text-amber-400"
                    }`}>
                      {v.status as string}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-xs text-foreground">{(v.found as string) || "—"}</td>
                  <td className="py-2 px-3 text-xs text-foreground">{(v.expected as string) || "—"}</td>
                  <td className="py-2 px-3">
                    <span className={`text-xs font-medium ${
                      v.severity === "critical" ? "text-destructive" :
                      v.severity === "major" ? "text-amber-400" : "text-muted-foreground"
                    }`}>
                      {v.severity as string}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground max-w-xs">{v.reasoning as string}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DecisionView({ data }: { data: Record<string, unknown> }) {
  const discrepancies = data.discrepancies as Record<string, unknown>[] | undefined;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className={`text-sm font-semibold px-3 py-1.5 rounded-full ${
          data.outcome === "auto_approve" ? "bg-emerald-500/10 text-emerald-500" :
          data.outcome === "human_review" ? "bg-amber-500/10 text-amber-400" :
          "bg-destructive/10 text-destructive"
        }`}>
          {(data.outcome as string)?.replace(/_/g, " ")}
        </span>
      </div>
      {data.reasoning && <div className="text-sm text-muted-foreground">{data.reasoning as string}</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b border-border">
              <th className="text-left font-medium py-2 pr-3">Field</th>
              <th className="text-left font-medium py-2 px-3">Severity</th>
              <th className="text-left font-medium py-2 px-3">Found</th>
              <th className="text-left font-medium py-2 px-3">Expected</th>
              <th className="text-left font-medium py-2 px-3">Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {discrepancies && discrepancies.length > 0 ? (
              discrepancies.map((d, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3 font-medium text-foreground">{(d.field as string)?.replace(/_/g, " ")}</td>
                  <td className="py-2 px-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      d.severity === "critical" ? "bg-destructive/10 text-destructive" :
                      d.severity === "major" ? "bg-amber-500/10 text-amber-400" :
                      "bg-muted text-muted-foreground"
                    }`}>
                      {d.severity as string}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-xs text-foreground">{(d.found as string) || "—"}</td>
                  <td className="py-2 px-3 text-xs text-foreground">{(d.expected as string) || "—"}</td>
                  <td className="py-2 px-3 text-xs text-muted-foreground max-w-xs">{d.reasoning as string}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="py-3 text-sm text-muted-foreground italic">
                  No discrepancies — all fields passed validation.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
