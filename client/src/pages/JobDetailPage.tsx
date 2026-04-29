import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, FileText, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DocumentStatusBadge, OutcomeBadge } from "@/components/StatusBadges";
import { getJob, startJob } from "@/services/api";
import type { JobDetail, JobStatus } from "@/services/types";
import { cn, formatBytes, formatRelative } from "@/lib/utils";

const STATUS_STYLES: Record<JobStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  processing: "bg-primary/10 text-primary",
  completed: "bg-emerald-500/10 text-emerald-500",
  partial_failure: "bg-amber-500/10 text-amber-400",
  failed: "bg-destructive/10 text-destructive",
};

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      const j = await getJob(id);
      setJob(j);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while processing.
  useEffect(() => {
    if (!job || job.status !== "processing") return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [job, load]);

  const onStart = async () => {
    if (!id) return;
    setStarting(true);
    try {
      await startJob(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  if (error && !job) {
    return (
      <div className="space-y-4">
        <Link to="/" className="text-sm text-primary hover:underline flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to jobs
        </Link>
        <div className="text-destructive">{error}</div>
      </div>
    );
  }

  if (!job) {
    return <div className="text-sm text-muted-foreground animate-pulse">Loading job…</div>;
  }

  const canStart = job.status === "pending";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              Job <span className="font-mono text-sm text-muted-foreground">{job.id.slice(0, 8)}…</span>
            </h1>
            <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
              <span>{job.document_count} documents</span>
              <span>·</span>
              <span>created {formatRelative(job.created_at)}</span>
              {job.started_at && (
                <>
                  <span>·</span>
                  <span>started {formatRelative(job.started_at)}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-medium px-2.5 py-1 rounded-full",
              STATUS_STYLES[job.status]
            )}
          >
            {job.status.replace(/_/g, " ")}
          </span>
          <Button variant="outline" size="sm" onClick={load} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          </Button>
          {canStart && (
            <Button onClick={onStart} disabled={starting}>
              <Play className="h-4 w-4 mr-1.5" />
              {starting ? "Starting…" : "Start processing"}
            </Button>
          )}
        </div>
      </div>

      {error && <div className="text-sm text-destructive">{error}</div>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Documents</CardTitle>
        </CardHeader>
        <CardContent>
          {job.documents.length === 0 ? (
            <div className="text-sm text-muted-foreground italic">No documents in this job.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="text-left font-medium py-2 pr-3">Name</th>
                    <th className="text-left font-medium py-2 px-3">Doc type</th>
                    <th className="text-left font-medium py-2 px-3">Size</th>
                    <th className="text-left font-medium py-2 px-3">Status</th>
                    <th className="text-left font-medium py-2 px-3">Outcome</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {job.documents.map((d) => (
                    <tr
                      key={d.id}
                      className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                    >
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="font-medium text-foreground truncate max-w-xs">
                            {d.original_name}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">
                        {d.doc_type?.replace(/_/g, " ") ?? "—"}
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">
                        {formatBytes(d.size_bytes)}
                      </td>
                      <td className="py-2.5 px-3">
                        <DocumentStatusBadge status={d.status} />
                      </td>
                      <td className="py-2.5 px-3">
                        {d.outcome ? <OutcomeBadge outcome={d.outcome} /> : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/documents/${d.id}`}>
                            Timeline <ArrowRight className="h-4 w-4 ml-1" />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
