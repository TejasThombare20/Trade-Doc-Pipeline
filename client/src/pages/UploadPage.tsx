import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { File as FileIcon, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { uploadDocuments } from "@/services/api";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.docx,application/pdf,image/*";
const MAX_BYTES = 25 * 1024 * 1024;

export function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<{ pct: number; loaded: number; total: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const addFiles = useCallback((incoming: FileList | File[]) => {
    setError(null);
    const next: File[] = [];
    for (const f of Array.from(incoming)) {
      if (f.size > MAX_BYTES) {
        setError(`'${f.name}' is ${formatBytes(f.size)}, max is ${formatBytes(MAX_BYTES)}.`);
        continue;
      }
      next.push(f);
    }
    setFiles((prev) => [...prev, ...next]);
  }, []);

  const removeAt = (i: number) => setFiles((prev) => prev.filter((_, idx) => idx !== i));

  const onUpload = async () => {
    if (files.length === 0) return;
    setError(null);
    setUploading(true);
    setProgress({ pct: 0, loaded: 0, total: files.reduce((s, f) => s + f.size, 0) });
    try {
      const res = await uploadDocuments(files, (pct, loaded, total) =>
        setProgress({ pct, loaded, total })
      );
      navigate(`/jobs/${res.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Upload documents</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Drop one or more trade documents. They'll be grouped into a single job that you can start when ready.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Select files</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div
            onDragOver={(e) => { e.preventDefault(); if (!uploading) setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (uploading) return;
              if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
            }}
            onClick={() => !uploading && inputRef.current?.click()}
            className={cn(
              "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
              dragOver ? "border-primary bg-primary/5" : "border-input bg-background",
              uploading && "opacity-50 cursor-not-allowed"
            )}
          >
            <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <div className="text-sm font-medium">Click or drag files here</div>
            <div className="text-xs text-muted-foreground mt-1">
              Bill of Lading · Commercial Invoice · Packing List · up to {formatBytes(MAX_BYTES)} each
            </div>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {error && <div className="text-sm text-destructive">{error}</div>}

          {files.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">
                {files.length} file{files.length !== 1 ? "s" : ""} selected
              </div>
              <ul className="space-y-1">
                {files.map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center gap-3 p-2 rounded-md border border-border bg-card"
                  >
                    <FileIcon className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{f.name}</div>
                      <div className="text-xs text-muted-foreground">{formatBytes(f.size)}</div>
                    </div>
                    {!uploading && (
                      <button
                        onClick={() => removeAt(i)}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>

              {progress && (
                <div>
                  <Progress value={progress.pct} />
                  <div className="mt-1 text-xs text-muted-foreground">
                    {progress.pct}% · {formatBytes(progress.loaded)} / {formatBytes(progress.total)}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <Button variant="outline" disabled={uploading} onClick={() => setFiles([])}>
                  Clear
                </Button>
                <Button disabled={uploading || files.length === 0} onClick={onUpload}>
                  {uploading ? "Uploading…" : `Upload ${files.length} file${files.length !== 1 ? "s" : ""}`}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        After upload, you'll land on the job page where you can review the files and click <strong>Start processing</strong> to run the pipeline.
      </p>
    </div>
  );
}
