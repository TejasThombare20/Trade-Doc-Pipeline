import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { getMe, signIn as apiSignIn, signOut as apiSignOut } from "@/services/api";
import type { SessionInfo } from "@/services/types";

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

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((data) => { if (!cancelled) setSession(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const signIn = useCallback(
    async (tenantSlug: string, role: "admin" | "default") => {
      const data = await apiSignIn(tenantSlug, role);
      setSession(data);
    },
    []
  );

  const signOut = useCallback(async () => {
    await apiSignOut();
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
