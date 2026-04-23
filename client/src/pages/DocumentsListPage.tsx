import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FileText, Inbox, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DocumentStatusBadge, OutcomeBadge } from "@/components/StatusBadges";
import { listDocuments } from "@/services/api";
import type { DocumentListItem } from "@/services/types";
import { formatRelative } from "@/lib/utils";

export function DocumentsListPage() {
  const [rows, setRows] = useState<DocumentListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<"all" | "document" | "rule_book">("all");

  const load = async () => {
    setRefreshing(true);
    try {
      setRows(await listDocuments());
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

  const filtered = rows?.filter((r) => filter === "all" || r.type === filter) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Documents</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            All trade documents and rule books for your tenant.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button asChild>
            <Link to="/upload">Upload document</Link>
          </Button>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-muted rounded-lg p-1 w-fit">
        {([
          { key: "all", label: "All" },
          { key: "document", label: "Documents" },
          { key: "rule_book", label: "Rule Books" },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setFilter(tab.key)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              filter === tab.key
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="pt-6">
          {error && <div className="text-sm text-destructive mb-3">{error}</div>}
          {filtered === null ? (
            <div className="text-sm text-muted-foreground animate-pulse">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Inbox className="h-10 w-10 mx-auto mb-2" />
              <div>No documents yet. Upload one to start the pipeline.</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="text-left font-medium py-2 pr-3">Name</th>
                    <th className="text-left font-medium py-2 px-3">Type</th>
                    <th className="text-left font-medium py-2 px-3">Doc type</th>
                    <th className="text-left font-medium py-2 px-3">Status</th>
                    <th className="text-left font-medium py-2 px-3">Outcome</th>
                    <th className="text-left font-medium py-2 px-3">Submitted</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.id} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2">
                          {r.type === "rule_book" ? (
                            <ShieldCheck className="h-4 w-4 text-primary flex-shrink-0" />
                          ) : (
                            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          )}
                          <span className="font-medium text-foreground truncate max-w-xs">
                            {r.original_name}
                          </span>
                          {r.is_active && (
                            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500">
                              active
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          r.type === "rule_book"
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground"
                        }`}>
                          {r.type === "rule_book" ? "rule book" : "document"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">
                        {r.doc_type?.replace(/_/g, " ") ?? "—"}
                      </td>
                      <td className="py-2.5 px-3">
                        <DocumentStatusBadge status={r.status} />
                      </td>
                      <td className="py-2.5 px-3">
                        {r.outcome ? (
                          <OutcomeBadge outcome={r.outcome} />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">
                        {formatRelative(r.created_at)}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/documents/${r.id}`}>
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
