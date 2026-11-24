"use client";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, Download, History } from "lucide-react";
import { authApi, meApi } from "@/lib/api";
import { format } from "date-fns";
import { useAuthStore } from "@/store/auth";
import type { User } from "@/types";

const GENDERS: { id: NonNullable<User["gender"]>; label: string }[] = [
  { id: "female", label: "Female" }, { id: "male", label: "Male" },
  { id: "non_binary", label: "Non-binary" }, { id: "prefer_not_to_say", label: "Prefer not to say" },
];
const THIS_YEAR = new Date().getFullYear();
const CONSENT_LABELS: Record<string, string> = {
  personalized_recs: "Personalised recommendations", profiling_consent: "Insights and partner offers",
  event_alerts: "Alerts about saved events", wrapped_opt_in: "Turnup Wrapped",
};

function Toggle({ checked, onChange, label, help, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; help: string; disabled?: boolean;
}) {
  return (
    <label className="flex items-start justify-between gap-3 cursor-pointer">
      <span>
        <span className="block text-sm font-bold text-text">{label}</span>
        <span className="block text-xs text-text-muted mt-0.5">{help}</span>
      </span>
      <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-primary"
        checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

/** Settings -> Your data: personalisation, the profiling opt-in, and optional age and gender
 *  (docs/recommendations-spec.md). */
export function DataSettings() {
  const { token, user, setUser } = useAuthStore();
  const [error, setError] = useState("");
  const save = useMutation({
    mutationFn: (body: Parameters<typeof authApi.updatePreferences>[1]) => authApi.updatePreferences(token!, body),
    onSuccess: (u) => { setUser(u); setError(""); },
    onError: () => setError("Couldn't save that. Check your connection and try again."),
  });
  const [showLog, setShowLog] = useState(false);
  const log = useQuery({
    queryKey: ["consents", user?.profiling_consent, user?.personalized_recs, user?.event_alerts, user?.wrapped_opt_in],
    queryFn: () => meApi.consents(token!), enabled: !!token && showLog,
  });
  const download = useMutation({
    mutationFn: () => meApi.exportData(token!),
    onSuccess: (data) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `turnup-data-${user?.username ?? "me"}-${format(new Date(), "yyyyMMdd")}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    onError: () => setError("Couldn't prepare your data. Try again in a minute."),
  });
  if (!user) return null;
  const busy = save.isPending;

  return (
    <section className="border-2 border-border rounded bg-bg-card p-4 space-y-4">
      <h2 className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-text">
        <Database size={16} /> Your data
      </h2>
      <p className="text-xs text-text-muted">
        Turnup records what you do in the app (events you view, search for, save and buy) to
        recommend events. It&apos;s deleted after 180 days, or straight away if you delete your account.
      </p>

      <Toggle
        label="Personalised recommendations"
        help="Use your activity to pick events for you. Off: you see what's popular near you."
        checked={user.personalized_recs ?? true} disabled={busy}
        onChange={(v) => save.mutate({ personalized_recs: v })}
      />
      <Toggle
        label="Alerts about events you saved"
        help="Tell me when an event I saved is almost sold out or its tickets get cheaper. At most one a day."
        checked={user.event_alerts ?? true} disabled={busy}
        onChange={(v) => save.mutate({ event_alerts: v })}
      />
      <Toggle
        label="Insights and partner offers"
        help="Also use your precise location (if you've allowed it), when you usually go out, who you
          often go with (if they've opted in too) and audience groups for brands that sponsor events.
          Off by default; turning it off deletes these."
        checked={!!user.profiling_consent} disabled={busy}
        onChange={(v) => save.mutate({ profiling_consent: v })}
      />

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className="block text-xs font-bold text-text">Year of birth <span className="text-text-muted font-normal">(optional)</span></span>
          <select className="w-full rounded border-2 border-border bg-bg px-2 py-2 text-sm text-text"
            value={user.birth_year ?? ""} disabled={busy}
            onChange={(e) => save.mutate({ birth_year: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Not given</option>
            {Array.from({ length: 80 }, (_, i) => THIS_YEAR - 13 - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-xs font-bold text-text">Gender <span className="text-text-muted font-normal">(optional)</span></span>
          <select className="w-full rounded border-2 border-border bg-bg px-2 py-2 text-sm text-text"
            value={user.gender ?? ""} disabled={busy}
            onChange={(e) => save.mutate({ gender: (e.target.value || null) as User["gender"] })}>
            <option value="">Not given</option>
            {GENDERS.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}

      <div className="flex flex-wrap gap-2 pt-1">
        <button onClick={() => download.mutate()} disabled={download.isPending}
          className="flex items-center gap-1.5 px-3 py-2 rounded border-2 border-border text-xs font-bold text-text hover:border-primary disabled:opacity-50">
          <Download size={14} aria-hidden /> {download.isPending ? "Preparing…" : "Download my data"}
        </button>
        <button onClick={() => setShowLog((v) => !v)} aria-expanded={showLog}
          className="flex items-center gap-1.5 px-3 py-2 rounded border-2 border-border text-xs font-bold text-text hover:border-primary">
          <History size={14} aria-hidden /> {showLog ? "Hide" : "Show"} consent history
        </button>
      </div>
      {showLog && (
        log.data && log.data.length > 0 ? (
          <ul className="text-xs divide-y divide-border">
            {log.data.map((c, i) => (
              <li key={i} className="py-1.5 flex justify-between gap-3">
                <span className="text-text">{CONSENT_LABELS[c.setting] ?? c.setting}: <strong>{c.value ? "on" : "off"}</strong></span>
                <span className="text-text-muted shrink-0">{format(new Date(c.changed_at), "d MMM yyyy, HH:mm")}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-text-muted">{log.isLoading ? "Loading…" : "You haven't changed any of these yet; they're at their defaults."}</p>
        )
      )}
    </section>
  );
}
