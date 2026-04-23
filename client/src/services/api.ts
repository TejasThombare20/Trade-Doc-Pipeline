import type {
  DocumentDetail,
  DocumentListItem,
  RuleBookBundle,
  RuleBookUploadResponse,
  TenantOption,
  UploadResponse,
} from "./types";

// All API calls use credentials: "include" so the httpOnly cookie is sent automatically.

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    const msg =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message: unknown }).message)
        : `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, detail);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail: unknown
  ) {
    super(message);
  }
}

// ---------- Auth ----------

export async function listTenants(): Promise<TenantOption[]> {
  const res = await fetch("/api/auth/tenants");
  return json<TenantOption[]>(res);
}

// ---------- Documents ----------

export async function listDocuments(): Promise<DocumentListItem[]> {
  const res = await fetch("/api/documents", { credentials: "include" });
  return json<DocumentListItem[]>(res);
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const res = await fetch(`/api/documents/${id}`, { credentials: "include" });
  return json<DocumentDetail>(res);
}

// Uses XHR so we get real upload progress events.
export function uploadDocument(
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    xhr.withCredentials = true;

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded, ev.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (e) {
          reject(e);
        }
      } else {
        let parsed: unknown = xhr.responseText;
        try { parsed = JSON.parse(xhr.responseText); } catch { /* ignore */ }
        const msg =
          typeof parsed === "object" && parsed && "message" in parsed
            ? String((parsed as { message: unknown }).message)
            : `HTTP ${xhr.status}`;
        reject(new ApiError(msg, xhr.status, parsed));
      }
    };
    xhr.onerror = () => reject(new ApiError("network_error", 0, null));
    xhr.send(form);
  });
}

// ---------- Rule books ----------

export async function listRuleBooks(): Promise<RuleBookBundle[]> {
  const res = await fetch("/api/rule-books", { credentials: "include" });
  return json<RuleBookBundle[]>(res);
}

export function uploadRuleBook(
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<RuleBookUploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/rule-books/upload");
    xhr.withCredentials = true;

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded, ev.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (e) {
          reject(e);
        }
      } else {
        let parsed: unknown = xhr.responseText;
        try { parsed = JSON.parse(xhr.responseText); } catch { /* ignore */ }
        const msg =
          typeof parsed === "object" && parsed && "message" in parsed
            ? String((parsed as { message: unknown }).message)
            : `HTTP ${xhr.status}`;
        reject(new ApiError(msg, xhr.status, parsed));
      }
    };
    xhr.onerror = () => reject(new ApiError("network_error", 0, null));
    xhr.send(form);
  });
}
