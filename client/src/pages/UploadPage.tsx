import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Timeline } from "@/components/Timeline";
import { UploadDropzone } from "@/components/UploadDropzone";
import { uploadDocument } from "@/services/api";

export function UploadPage() {
  const [progress, setProgress] = useState<{ pct: number; loaded: number; total: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (file: File) => {
    setError(null);
    setUploading(true);
    setDocumentId(null);
    setSessionId(null);
    setProgress({ pct: 0, loaded: 0, total: file.size });
    try {
      const res = await uploadDocument(file, (pct, loaded, total) =>
        setProgress({ pct, loaded, total })
      );
      setDocumentId(res.document_id);
      setSessionId(res.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    setDocumentId(null);
    setSessionId(null);
    setProgress(null);
    setError(null);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Upload document</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Drop a trade document and watch the pipeline run.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload file</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadDropzone
            disabled={uploading || !!documentId}
            accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,application/pdf,image/*"
            onFile={onFile}
            progress={progress}
            help="Bill of Lading · Commercial Invoice · Packing List"
            uploadError={error}
          />
          {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
        </CardContent>
      </Card>

      {documentId && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Pipeline</CardTitle>
            <div className="flex gap-2">
              <Button variant="outline" onClick={reset}>Upload another</Button>
              <Button asChild>
                <Link to={`/documents/${documentId}`}>
                  View full detail <ArrowRight className="h-4 w-4 ml-1" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Timeline documentId={documentId} sessionId={sessionId} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
