import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export interface SessionInfo {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: "admin" | "default";
  session_id: string;
}

interface AuthContextValue {
  session: SessionInfo | null;
  loading: boolean;
  signIn: (tenantSlug: string, role: "admin" | "default") => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  session: null,
  loading: true,
  signIn: async () => {},
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, try to restore session from cookie via /api/auth/me
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setSession(data);
        }
      } catch {
        // not signed in
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(
    async (tenantSlug: string, role: "admin" | "default") => {
      const res = await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ tenant_slug: tenantSlug, role }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ message: "Sign in failed" }));
        throw new Error(err.message || `HTTP ${res.status}`);
      }
      const data: SessionInfo = await res.json();
      setSession(data);
    },
    []
  );

  const signOut = useCallback(async () => {
    await fetch("/api/auth/signout", {
      method: "POST",
      credentials: "include",
    });
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
