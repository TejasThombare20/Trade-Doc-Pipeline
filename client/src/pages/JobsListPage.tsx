import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Inbox, Layers, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { listJobs } from "@/services/api";
import type { JobListItem, JobStatus } from "@/services/types";
import { formatRelative } from "@/lib/utils";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<JobStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  processing: "bg-primary/10 text-primary",
  completed: "bg-emerald-500/10 text-emerald-500",
  partial_failure: "bg-amber-500/10 text-amber-400",
  failed: "bg-destructive/10 text-destructive",
};

export function JobsListPage() {
  const [rows, setRows] = useState<JobListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      setRows(await listJobs());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Jobs</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Each job groups the documents you uploaded together. Click a job to view its documents.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button asChild>
            <Link to="/upload">Upload documents</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          {error && <div className="text-sm text-destructive mb-3">{error}</div>}
          {rows === null ? (
            <div className="text-sm text-muted-foreground animate-pulse">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Inbox className="h-10 w-10 mx-auto mb-2" />
              <div>No jobs yet. Upload documents to start one.</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="text-left font-medium py-2 pr-3">Job</th>
                    <th className="text-left font-medium py-2 px-3">Documents</th>
                    <th className="text-left font-medium py-2 px-3">Status</th>
                    <th className="text-left font-medium py-2 px-3">Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((j) => (
                    <tr
                      key={j.id}
                      className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors"
                    >
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2">
                          <Layers className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="font-medium text-foreground font-mono text-xs">
                            {j.id.slice(0, 8)}…
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground">
                        {j.document_count} {j.document_count === 1 ? "document" : "documents"}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={cn(
                            "text-xs font-medium px-2 py-0.5 rounded-full",
                            STATUS_STYLES[j.status]
                          )}
                        >
                          {j.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">
                        {formatRelative(j.created_at)}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/jobs/${j.id}`}>
                            Open <ArrowRight className="h-4 w-4 ml-1" />
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
