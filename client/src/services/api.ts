import axios, { AxiosError } from "axios";
import type {
  CreateJobResponse,
  DocumentDetail,
  JobDetail,
  JobListItem,
  RuleBookBundle,
  RuleBookUploadResponse,
  SessionInfo,
  StartJobResponse,
  TenantOption,
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
  baseURL: "/v1",
  withCredentials: true,
});

// Response interceptor: unwrap {data, message, statusCode} envelope.
http.interceptors.response.use(
  (res) => {
    if (res.data && typeof res.data === "object" && "data" in res.data) {
      res.data = res.data.data;
    }
    return res;
  },
  (err: AxiosError<{ message?: string; statusCode?: number }>) => {
    const status = err.response?.status ?? 0;
    const data = err.response?.data;
    const message =
      data?.message ?? (status === 0 ? "network_error" : `HTTP ${status}`);
    const code = String(data?.statusCode ?? (status || "unknown_error"));
    return Promise.reject(new ApiError(message, status, code, data ?? null));
  }
);

// ─── auth ─────────────────────────────────────────────────────────────────────

export async function listTenants(): Promise<TenantOption[]> {
  const res = await http.get<TenantOption[]>("/auth/tenants");
  return res.data;
}

export async function signIn(tenantSlug: string, role: "admin" | "default"): Promise<SessionInfo> {
  const res = await http.post<SessionInfo>("/auth/session", { tenant_slug: tenantSlug, role });
  return res.data;
}

export async function signOut(): Promise<void> {
  await http.post("/auth/signout");
}

export async function getMe(): Promise<SessionInfo> {
  const res = await http.get<SessionInfo>("/auth/me");
  return res.data;
}

// ─── jobs ─────────────────────────────────────────────────────────────────────

export async function listJobs(): Promise<JobListItem[]> {
  const res = await http.get<JobListItem[]>("/jobs");
  return res.data;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const res = await http.get<JobDetail>(`/jobs/${jobId}`);
  return res.data;
}

export async function startJob(jobId: string): Promise<StartJobResponse> {
  const res = await http.post<StartJobResponse>(`/jobs/${jobId}/start`);
  return res.data;
}

export async function deleteJob(jobId: string): Promise<void> {
  await http.delete(`/jobs/${jobId}`);
}

// ─── documents (multi-file upload creates a job) ──────────────────────────────

export async function uploadDocuments(
  files: File[],
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<CreateJobResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await http.post<CreateJobResponse>("/documents", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress(ev) {
      if (ev.total) {
        onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded, ev.total);
      }
    },
  });
  return res.data;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const res = await http.get<DocumentDetail>(`/documents/${id}`);
  return res.data;
}

export async function getFileUrl(documentId: string): Promise<{ url: string; expires_at: string }> {
  // /v1/files/{id} returns JSON {url, expires_at} — not wrapped in the envelope.
  const res = await http.get<{ url: string; expires_at: string }>(`/files/${documentId}`);
  return res.data;
}

// ─── rule books ───────────────────────────────────────────────────────────────

export async function listRuleBooks(): Promise<RuleBookBundle[]> {
  const res = await http.get<RuleBookBundle[]>("/rule-books");
  return res.data;
}

export async function getRuleBook(id: string): Promise<RuleBookBundle> {
  const res = await http.get<RuleBookBundle>(`/rule-books/${id}`);
  return res.data;
}

export function uploadRuleBook(
  file: File,
  onProgress: (pct: number, loaded: number, total: number) => void
): Promise<RuleBookUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return http
    .post<RuleBookUploadResponse>("/rule-books/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress(ev) {
        if (ev.total) {
          onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded, ev.total);
        }
      },
    })
    .then((r) => r.data);
}
