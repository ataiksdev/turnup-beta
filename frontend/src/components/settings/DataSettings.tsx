"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { User } from "@/types";

const GENDERS: { id: NonNullable<User["gender"]>; label: string }[] = [
  { id: "female", label: "Female" }, { id: "male", label: "Male" },
  { id: "non_binary", label: "Non-binary" }, { id: "prefer_not_to_say", label: "Prefer not to say" },
];
const THIS_YEAR = new Date().getFullYear();

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
    </section>
  );
}
