import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { listCustomers } from "@/services/api";
import type { Customer } from "@/services/types";
import { useAuth } from "@/contexts/AuthContext";

export interface CustomerPickerProps {
  value: string | null;
  onChange: (id: string) => void;
  requireActiveRuleBook?: boolean;
}

export function CustomerPicker({ value, onChange, requireActiveRuleBook }: CustomerPickerProps) {
  const { session } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.tenant_id) return;
    let cancelled = false;
    listCustomers(session.tenant_id)
      .then((cs) => { if (!cancelled) setCustomers(cs); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [session?.tenant_id]);

  const current = customers.find((c) => c.id === value) ?? null;
  const blocked =
    requireActiveRuleBook && current !== null && !current.has_active_rule_book;

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Customer</label>
      <Select value={value ?? undefined} onValueChange={onChange} disabled={loading || !!error}>
        <SelectTrigger>
          <SelectValue placeholder={loading ? "Loading…" : "Pick a customer"} />
        </SelectTrigger>
        <SelectContent>
          {customers.map((c) => (
            <SelectItem key={c.id} value={c.id}>
              <div className="flex items-center gap-2">
                <span>{c.name}</span>
                <span className="text-xs text-muted-foreground">({c.code})</span>
                {!c.has_active_rule_book && (
                  <span className="text-xs text-amber-700">· no rule book</span>
                )}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <div className="text-sm text-red-600">Failed to load customers: {error}</div>}
      {blocked && (
        <div className="flex items-center gap-2 text-sm text-amber-700">
          <AlertTriangle className="h-4 w-4" />
          This customer has no active rule book. Upload one in the admin page first.
        </div>
      )}
    </div>
  );
}
