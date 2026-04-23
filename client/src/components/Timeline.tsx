import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Cpu,
  Loader2,
  Wrench,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TimelineStep, SSEEvent } from "@/services/types";

const STEP_LABELS: Record<string, string> = {
  parsing: "Parsing",
  extraction: "Extraction",
  validation: "Validation",
  decision: "Decision",
};

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  parsing: Wrench,
  extraction: Zap,
  validation: CheckCircle2,
  decision: Cpu,
};

function StepIcon({ stepType, status }: { stepType: string; status: string }) {
  if (status === "success") return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
  if (status === "pending" && stepType !== "parsing") return <Loader2 className="h-5 w-5 text-primary animate-spin" />;
  if (status === "pending" && stepType === "parsing") return <Loader2 className="h-5 w-5 text-amber-500 animate-spin" />;
  if (status === "fail") return <AlertCircle className="h-5 w-5 text-destructive" />;
  const Icon = STEP_ICONS[stepType] || Circle;
  return <Icon className="h-5 w-5 text-muted-foreground" />;
}

interface TimelineProps {
  documentId: string;
  sessionId: string | null;
}

export function Timeline({ documentId, sessionId }: TimelineProps) {
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalTokensIn, setTotalTokensIn] = useState(0);
  const [totalTokensOut, setTotalTokensOut] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!documentId) return;

    const url = `/api/documents/${documentId}/timeline`;
    const es = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };

    es.onerror = () => {
      setConnected(false);
    };

    const handleEvent = (e: MessageEvent) => {
      try {
        const data: SSEEvent = JSON.parse(e.data);

        if (data.event === "snapshot") {
          setSteps(data.steps || []);
          setPipelineStatus(data.pipeline_status || null);
          if (data.total_tokens_in) setTotalTokensIn(data.total_tokens_in);
          if (data.total_tokens_out) setTotalTokensOut(data.total_tokens_out);
          return;
        }

        if (data.event === "step_started") {
          setSteps((prev) => {
            const existing = prev.find((s) => s.id === data.run_id);
            if (existing) return prev;
            return [
              ...prev,
              {
                id: data.run_id,
                step_type: data.step_type,
                mode: data.mode || "llm",
                status: "pending",
                response: null,
                tokens_in: null,
                tokens_out: null,
                started_at: new Date().toISOString(),
                completed_at: null,
              },
            ];
          });
          return;
        }

        if (data.event === "step_completed") {
          setSteps((prev) =>
            prev.map((s) =>
              s.id === data.run_id
                ? {
                    ...s,
                    status: (data.status as "success" | "fail") || "success",
                    response: data.response || null,
                    tokens_in: data.tokens_in ?? null,
                    tokens_out: data.tokens_out ?? null,
                    completed_at: new Date().toISOString(),
                  }
                : s
            )
          );
          if (data.tokens_in) setTotalTokensIn((p) => p + (data.tokens_in || 0));
          if (data.tokens_out) setTotalTokensOut((p) => p + (data.tokens_out || 0));
          return;
        }

        if (data.event === "session_completed") {
          setPipelineStatus(data.status || "success");
          if (data.total_tokens_in) setTotalTokensIn(data.total_tokens_in);
          if (data.total_tokens_out) setTotalTokensOut(data.total_tokens_out);
          return;
        }

        if (data.event === "closed") {
          es.close();
          return;
        }
      } catch {
        // ignore parse errors
      }
    };

    for (const name of [
      "snapshot",
      "step_started",
      "step_completed",
      "session_started",
      "session_completed",
      "closed",
      "message",
    ]) {
      es.addEventListener(name, handleEvent);
    }

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [documentId]);

  const isRunning = pipelineStatus === "pending" || pipelineStatus === null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-medium",
            pipelineStatus === "success" && "bg-emerald-500/10 text-emerald-500",
            pipelineStatus === "fail" && "bg-destructive/10 text-destructive",
            isRunning && "bg-primary/10 text-primary"
          )}
        >
          {isRunning && <Loader2 className="h-3 w-3 animate-spin" />}
          {pipelineStatus === "success" && <CheckCircle2 className="h-3 w-3" />}
          {pipelineStatus === "fail" && <AlertCircle className="h-3 w-3" />}
          {pipelineStatus === "success"
            ? "Completed"
            : pipelineStatus === "fail"
            ? "Failed"
            : "Running"}
        </span>
        {(totalTokensIn > 0 || totalTokensOut > 0) && (
          <span className="text-muted-foreground">
            tokens: {totalTokensIn.toLocaleString()} in / {totalTokensOut.toLocaleString()} out
          </span>
        )}
      </div>

      {steps.length === 0 && isRunning && (
        <div className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Waiting for pipeline to start…
        </div>
      )}

      <ol className="relative border-l-2 border-border pl-6 space-y-6">
        {steps.map((step) => (
          <li key={step.id} className="relative">
            <span className="absolute -left-[31px] top-0.5 bg-card p-0.5 rounded-full border-2 border-border">
              <StepIcon stepType={step.step_type} status={step.status} />
            </span>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">
                    {STEP_LABELS[step.step_type] ?? step.step_type}
                  </span>
                  <span
                    className={cn(
                      "text-xs font-medium px-2 py-0.5 rounded-full",
                      step.status === "success" && "bg-emerald-500/10 text-emerald-500",
                      step.status === "fail" && "bg-destructive/10 text-destructive",
                      step.status === "pending" && "bg-primary/10 text-primary"
                    )}
                  >
                    {step.status}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {step.mode === "manual" ? "library" : "LLM"}
                  </span>
                </div>
                {step.tokens_in != null && step.tokens_out != null && (
                  <div className="text-xs text-muted-foreground">
                    {step.tokens_in + step.tokens_out} tokens
                  </div>
                )}
              </div>

              {step.response && step.status === "success" && (
                <StepResponsePreview stepType={step.step_type} response={step.response} />
              )}

              {step.response && step.status === "fail" && (
                <div className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                  {(step.response as Record<string, unknown>)?.error as string || "Step failed"}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StepResponsePreview({
  stepType,
  response,
}: {
  stepType: string;
  response: Record<string, unknown>;
}) {
  if (stepType === "parsing") {
    return (
      <div className="text-sm bg-muted rounded-lg p-3 space-y-1 border border-border">
        <div className="text-muted-foreground">
          <span className="font-medium text-foreground">{response.source_kind as string}</span>
          {" · "}
          {response.page_count as number} page{(response.page_count as number) !== 1 ? "s" : ""}
          {" · "}
          {response.text_len as number} chars
          {response.image_count ? ` · ${response.image_count} images` : ""}
        </div>
        {response.notes && (
          <div className="text-xs text-amber-500">{response.notes as string}</div>
        )}
      </div>
    );
  }

  if (stepType === "extraction") {
    const toolOutput = (response.tool_output || response) as Record<string, unknown>;
    const fields = toolOutput.fields as Record<string, Record<string, unknown>> | undefined;
    const docType = toolOutput.doc_type as string;
    if (!fields) {
      return (
        <pre className="text-xs bg-muted rounded-lg p-3 overflow-x-auto border border-border max-h-64 text-muted-foreground">
          {JSON.stringify(response, null, 2)}
        </pre>
      );
    }
    const entries = Object.entries(fields);
    const present = entries.filter(([, f]) => f.value != null);
    return (
      <div className="bg-muted rounded-lg p-3 border border-border space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-foreground">{docType?.replace(/_/g, " ")}</span>
          <span className="text-xs text-muted-foreground">{present.length}/{entries.length} fields extracted</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {entries.map(([name, f]) => (
            <div key={name} className="text-xs flex items-start gap-1.5">
              <span className={cn(
                "inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0",
                f.value != null
                  ? (f.confidence as number) >= 0.7
                    ? "bg-emerald-500"
                    : "bg-amber-500"
                  : "bg-muted-foreground"
              )} />
              <span className="text-muted-foreground min-w-0">
                <span className="font-medium text-foreground">{name.replace(/_/g, " ")}:</span>{" "}
                {f.value != null ? (
                  <span>{f.value as string}</span>
                ) : (
                  <span className="italic">absent</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (stepType === "validation") {
    const toolOutput = (response.tool_output || response) as Record<string, unknown>;
    const results = toolOutput.results as Record<string, Record<string, unknown>> | undefined;
    const overallStatus = toolOutput.overall_status as string;
    const summary = toolOutput.summary as string;
    if (!results) {
      return (
        <pre className="text-xs bg-muted rounded-lg p-3 overflow-x-auto border border-border max-h-64 text-muted-foreground">
          {JSON.stringify(response, null, 2)}
        </pre>
      );
    }
    const entries = Object.entries(results);
    return (
      <div className="bg-muted rounded-lg p-3 border border-border space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <span className={cn(
            "font-medium",
            overallStatus === "all_match" && "text-emerald-500",
            overallStatus === "has_uncertain" && "text-amber-400",
            overallStatus === "has_mismatch" && "text-destructive"
          )}>
            {overallStatus?.replace(/_/g, " ")}
          </span>
        </div>
        {summary && <div className="text-xs text-muted-foreground">{summary}</div>}
        <div className="space-y-1">
          {entries.map(([name, v]) => (
            <div key={name} className="text-xs flex items-start gap-1.5">
              <span className={cn(
                "inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0",
                v.status === "match" && "bg-emerald-500",
                v.status === "mismatch" && "bg-destructive",
                v.status === "uncertain" && "bg-amber-500"
              )} />
              <span className="text-muted-foreground min-w-0">
                <span className="font-medium text-foreground">{name.replace(/_/g, " ")}</span>
                {" — "}
                <span className={cn(
                  v.status === "match" && "text-emerald-500",
                  v.status === "mismatch" && "text-destructive",
                  v.status === "uncertain" && "text-amber-400"
                )}>
                  {v.status as string}
                </span>
                {v.reasoning && (
                  <span className="text-muted-foreground"> · {v.reasoning as string}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (stepType === "decision") {
    const toolOutput = (response.tool_output || response) as Record<string, unknown>;
    const outcome = toolOutput.outcome as string;
    const reasoning = toolOutput.reasoning as string;
    const discrepancies = toolOutput.discrepancies as Record<string, unknown>[] | undefined;
    return (
      <div className="bg-muted rounded-lg p-3 border border-border space-y-2">
        <div className="flex items-center gap-2">
          <span className={cn(
            "text-sm font-semibold px-2.5 py-1 rounded-full",
            outcome === "auto_approve" && "bg-emerald-500/10 text-emerald-500",
            outcome === "human_review" && "bg-amber-500/10 text-amber-400",
            outcome === "draft_amendment" && "bg-destructive/10 text-destructive"
          )}>
            {outcome?.replace(/_/g, " ")}
          </span>
        </div>
        {reasoning && <div className="text-xs text-muted-foreground">{reasoning}</div>}
        {discrepancies && discrepancies.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground">Discrepancies:</div>
            {discrepancies.map((d, i) => (
              <div key={i} className="text-xs text-muted-foreground pl-2 border-l-2 border-border">
                <span className="font-medium text-foreground">{d.field as string}</span>
                {" — "}
                <span className={cn(
                  (d.severity as string) === "critical" && "text-destructive",
                  (d.severity as string) === "major" && "text-amber-400",
                  (d.severity as string) === "minor" && "text-muted-foreground"
                )}>
                  {d.severity as string}
                </span>
                {d.reasoning && <span className="text-muted-foreground"> · {d.reasoning as string}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <pre className="text-xs bg-muted rounded-lg p-3 overflow-x-auto border border-border max-h-48 text-muted-foreground">
      {JSON.stringify(response, null, 2)}
    </pre>
  );
}
