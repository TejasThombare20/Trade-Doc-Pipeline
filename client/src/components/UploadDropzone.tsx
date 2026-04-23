import { useCallback, useEffect, useRef, useState } from "react";
import { File as FileIcon, Upload } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

export interface UploadDropzoneProps {
  disabled?: boolean;
  accept?: string;
  maxBytes?: number;
  onFile: (file: File) => void;
  progress?: { pct: number; loaded: number; total: number } | null;
  help?: string;
  uploadError?: string | null;
}

export function UploadDropzone({
  disabled,
  accept,
  maxBytes = 25 * 1024 * 1024,
  onFile,
  progress,
  help,
  uploadError,
}: UploadDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = useCallback((file: File) => {
    setError(null);
    if (file.size > maxBytes) {
      setError(`File is ${formatBytes(file.size)}, max is ${formatBytes(maxBytes)}.`);
      return;
    }
    setPreview(file);
    onFile(file);
  }, [maxBytes, onFile]);

  useEffect(() => {
    if (!progress || progress.pct < 100) return;
    // After upload completes, the parent will reset the preview indirectly.
  }, [progress]);

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (disabled) return;
          const file = e.dataTransfer.files?.[0];
          if (file) handle(file);
        }}
        onClick={() => !disabled && inputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          dragOver ? "border-primary bg-primary/5" : "border-input bg-background",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
        <div className="text-sm font-medium">Click or drag a file here</div>
        <div className="text-xs text-muted-foreground mt-1">
          {help ?? "PDF, PNG/JPG, or DOCX"} · up to {formatBytes(maxBytes)}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handle(f);
            e.target.value = "";
          }}
        />
      </div>

      {error && <div className="mt-2 text-sm text-red-600">{error}</div>}

      {preview && !uploadError && (
        <div className="mt-3 flex items-center gap-3 p-3 rounded-md border border-border bg-card">
          <FileIcon className="h-5 w-5 text-muted-foreground" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{preview.name}</div>
            <div className="text-xs text-muted-foreground">
              {formatBytes(preview.size)} · {preview.type || "unknown"}
            </div>
            {progress && (
              <div className="mt-2">
                <Progress value={progress.pct} />
                <div className="mt-1 text-xs text-muted-foreground">
                  {progress.pct}% · {formatBytes(progress.loaded)} / {formatBytes(progress.total)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
