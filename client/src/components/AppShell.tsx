import { Link, NavLink, Outlet } from "react-router-dom";
import { FileText, Layers, LogOut, ShieldCheck, Upload, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

const nav = [
  { to: "/", label: "Jobs", icon: Layers, end: true },
  { to: "/upload", label: "Upload", icon: Upload },
  { to: "/admin/rule-books", label: "Rule books", icon: ShieldCheck },
];

export function AppShell() {
  const { session, signOut } = useAuth();

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto max-w-7xl px-4 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
              <FileText className="h-4 w-4 text-white" />
            </div>
            <span className="text-foreground">Nova</span>
            <span className="text-xs text-muted-foreground font-normal hidden sm:inline">Trade Doc Pipeline</span>
          </Link>

          <nav className="flex items-center gap-1">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "px-3 h-9 inline-flex items-center gap-2 rounded-md text-sm transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </NavLink>
            ))}
          </nav>

          {session && (
            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-2 text-xs">
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-muted text-muted-foreground">
                  <User className="h-3.5 w-3.5" />
                  <span className="font-medium text-foreground">{session.tenant_name}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className={cn(
                    "font-medium",
                    session.role === "admin" ? "text-primary" : "text-muted-foreground"
                  )}>
                    {session.role}
                  </span>
                </div>
              </div>
              <button
                onClick={signOut}
                className="inline-flex items-center gap-1.5 px-3 h-8 rounded-md text-sm
                           text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
