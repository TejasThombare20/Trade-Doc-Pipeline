import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { listTenants } from "@/services/api";
import type { TenantOption } from "@/services/types";
import { FileText } from "lucide-react";

export function SignInPage() {
  const { session, signIn } = useAuth();
  const navigate = useNavigate();
  const [tenants, setTenants] = useState<TenantOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [role, setRole] = useState<"default" | "admin">("admin");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // If already signed in, redirect
  useEffect(() => {
    if (session) navigate("/", { replace: true });
  }, [session, navigate]);

  // Load available tenants
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ts = await listTenants();
        if (!cancelled) {
          setTenants(ts);
          if (ts.length > 0) setSelectedSlug(ts[0].slug);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load tenants");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlug) return;
    setError(null);
    setSubmitting(true);
    try {
      await signIn(selectedSlug, role);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-900 relative overflow-hidden">
      {/* Decorative elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-600/5 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md px-4">
        <div className="backdrop-blur-xl bg-white/10 border border-white/20 rounded-2xl shadow-2xl p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-indigo-500/20 border border-indigo-400/30 mb-4">
              <FileText className="h-7 w-7 text-indigo-300" />
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Nova</h1>
            <p className="text-sm text-slate-400 mt-1">Trade Document Pipeline</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Tenant select */}
            <div>
              <label htmlFor="tenant-select" className="block text-sm font-medium text-slate-300 mb-1.5">
                Organization
              </label>
              {loading ? (
                <div className="h-11 rounded-lg bg-white/5 border border-white/10 animate-pulse" />
              ) : (
                <select
                  id="tenant-select"
                  value={selectedSlug}
                  onChange={(e) => setSelectedSlug(e.target.value)}
                  className="w-full h-11 px-3 rounded-lg bg-white/5 border border-white/15 text-white
                             focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-400/50
                             transition-all appearance-none cursor-pointer"
                >
                  {tenants.map((t) => (
                    <option key={t.slug} value={t.slug} className="bg-slate-800 text-white">
                      {t.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Role select */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Role
              </label>
              <div className="grid grid-cols-2 gap-2">
                {(["admin", "default"] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setRole(r)}
                    className={`h-10 rounded-lg text-sm font-medium transition-all border ${
                      role === r
                        ? "bg-indigo-500/20 border-indigo-400/50 text-indigo-200 ring-1 ring-indigo-500/30"
                        : "bg-white/5 border-white/10 text-slate-400 hover:bg-white/10 hover:text-slate-200"
                    }`}
                  >
                    {r === "admin" ? "Admin" : "Operator"}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!selectedSlug || submitting || loading}
              className="w-full h-11 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium
                         transition-all disabled:opacity-50 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:ring-offset-2 focus:ring-offset-slate-900"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-xs text-slate-500 text-center mt-6">
            No password required in dev mode. Pick a tenant and role.
          </p>
        </div>
      </div>
    </div>
  );
}
