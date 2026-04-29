import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { AppShell } from "./components/AppShell";
import { SignInPage } from "./pages/SignInPage";
import { JobsListPage } from "./pages/JobsListPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { UploadPage } from "./pages/UploadPage";
import { RuleBooksPage } from "./pages/RuleBooksPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </div>
    );
  }
  if (!session) return <Navigate to="/sign-in" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<JobsListPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="jobs/:id" element={<JobDetailPage />} />
          <Route path="documents/:id" element={<DocumentDetailPage />} />
          <Route path="admin/rule-books" element={<RuleBooksPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
