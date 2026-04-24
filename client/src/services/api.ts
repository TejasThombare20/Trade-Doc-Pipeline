import axios, { AxiosError } from "axios";
import type {
  DocumentDetail,
  DocumentListItem,
  RuleBookBundle,
  RuleBookUploadResponse,
  TenantOption,
  UploadResponse,
} from "./types";

// ─── error class ─────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public detail: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ─── axios instance ───────────────────────────────────────────────────────────

const http = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

// Response interceptor: turn every non-2xx into ApiError with the backend's
// {code, message} shape so callers get a clean, typed error.
http.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ code?: string; message?: string; detail?: unknown }>) => {
    const status = err.response?.status ?? 0;
    const data = err.response?.data;
    const message =
      data?.message ??
      (status === 0 ? "network_error" : `HTTP ${status}`);
    const code = data?.code ?? "unknown_error";
    const detail = data?.detail ?? data ?? null;
    return Promise.reject(new ApiError(message, status, code, detail));
  }
);

// ─── helpers ─────────────────────────────────────────────────────────────────

async function uploadWithProgress<T>(
  url: string,
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await http.post<T>(url, form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress(ev) {
      if (ev.total) {
        onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded, ev.total);
      }
    },
  });
  return res.data;
}

// ─── auth ─────────────────────────────────────────────────────────────────────

export async function listTenants(): Promise<TenantOption[]> {
  const res = await http.get<TenantOption[]>("/auth/tenants");
  return res.data;
}

// ─── documents ────────────────────────────────────────────────────────────────

export async function listDocuments(): Promise<DocumentListItem[]> {
  const res = await http.get<DocumentListItem[]>("/documents");
  return res.data;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const res = await http.get<DocumentDetail>(`/documents/${id}`);
  return res.data;
}

export function uploadDocument(
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<UploadResponse> {
  return uploadWithProgress<UploadResponse>("/documents/upload", file, onProgress);
}

// ─── rule books ───────────────────────────────────────────────────────────────

export async function listRuleBooks(): Promise<RuleBookBundle[]> {
  const res = await http.get<RuleBookBundle[]>("/rule-books");
  return res.data;
}

export function uploadRuleBook(
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<RuleBookUploadResponse> {
  return uploadWithProgress<RuleBookUploadResponse>("/rule-books/upload", file, onProgress);
}

// ─── customers ────────────────────────────────────────────────────────────────

export async function listCustomers(tenantId: string) {
  const res = await http.get("/customers", { params: { tenant_id: tenantId } });
  return res.data;
}
