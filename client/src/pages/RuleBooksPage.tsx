import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Timeline } from "@/components/Timeline";
import { UploadDropzone } from "@/components/UploadDropzone";
import { listRuleBooks, uploadRuleBook } from "@/services/api";
import type { RuleBookBundle } from "@/services/types";
import { formatBytes, formatRelative } from "@/lib/utils";

export function RuleBooksPage() {
  const [ruleBooks, setRuleBooks] = useState<RuleBookBundle[] | null>(null);
  const [loadingBooks, setLoadingBooks] = useState(true);
  const [progress, setProgress] = useState<{ pct: number; loaded: number; total: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null);
  const [uploadedSessionId, setUploadedSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadBooks = async () => {
    setLoadingBooks(true);
    try {
      const books = await listRuleBooks();
      setRuleBooks(books);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingBooks(false);
    }
  };

  useEffect(() => { loadBooks(); }, []);

  const onFile = async (file: File) => {
    setError(null);
    setUploading(true);
    setUploadedDocId(null);
    setUploadedSessionId(null);
    setProgress({ pct: 0, loaded: 0, total: file.size });
    try {
      const res = await uploadRuleBook(file, (pct, loaded, total) =>
        setProgress({ pct, loaded, total })
      );
      setUploadedDocId(res.document_id);
      setUploadedSessionId(res.session_id);
      setTimeout(loadBooks, 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-indigo-500" />
          Rule Books
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Upload rule books. Rules are extracted via LLM and used to validate trade documents.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Existing Rule Books</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingBooks ? (
            <div className="text-sm text-muted-foreground animate-pulse">Loading…</div>
          ) : ruleBooks && ruleBooks.length > 0 ? (
            <div className="space-y-3">
              {ruleBooks.map((rb) => (
                <div
                  key={rb.document.id}
                  className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <ShieldCheck className={`h-5 w-5 ${rb.document.is_active ? "text-emerald-500" : "text-muted-foreground"}`} />
                    <div>
                      <div className="text-sm font-medium flex items-center gap-2">
                        {rb.document.original_name}
                        {rb.document.is_active && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500">
                            active
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                        <span>{formatBytes(rb.document.size_bytes)}</span>
                        <span>·</span>
                        <span>{rb.document.status}</span>
                        <span>·</span>
                        <span>{formatRelative(rb.document.created_at)}</span>
                        {rb.extracted_rules && (
                          <>
                            <span>·</span>
                            <span>{rb.extracted_rules.length} rules</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {rb.document.file_url && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.open(rb.document.file_url, "_blank")}
                      >
                        View file
                      </Button>
                    )}
                    <Button asChild size="sm" variant="ghost">
                      <Link to={`/documents/${rb.document.id}`}>
                        Details <ArrowRight className="h-4 w-4 ml-1" />
                      </Link>
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground text-center py-6">
              No rule books uploaded yet.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload New Rule Book</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadDropzone
            disabled={uploading || !!uploadedDocId}
            accept=".pdf,.docx,application/pdf"
            onFile={onFile}
            progress={progress}
            help="PDF or DOCX containing compliance rules"
          />
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
        </CardContent>
      </Card>

      {uploadedDocId && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Extraction Pipeline</CardTitle>
            <Button asChild size="sm">
              <Link to={`/documents/${uploadedDocId}`}>
                View detail <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <Timeline documentId={uploadedDocId} sessionId={uploadedSessionId} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
