"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AgentConnectionOut, AgentConnectionCreated, AgentSubmissionOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Bot, Copy, Check, KeyRound, Pencil, X as XIcon, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never";
  const m = Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(dateStr).toLocaleDateString("en-NG", { day: "2-digit", month: "short" });
}

function apiBase(): string {
  if (typeof window === "undefined") return "/api/integrations/v1";
  return `${window.location.origin}/api/integrations/v1`;
}

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-black text-text-secondary uppercase tracking-widest">{label}</p>
      <div className="flex items-stretch gap-2">
        <code className="flex-1 min-w-0 break-all text-xs font-mono bg-bg-elevated border-2 border-border rounded px-2 py-1.5">{value}</code>
        <Button size="sm" variant="secondary" aria-label={`Copy ${label}`} onClick={async () => {
          try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
        }}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </Button>
      </div>
    </div>
  );
}

/** Shown right after creating or rotating: the only time the key and secret are visible. */
function NewCredentials({ conn, onDone }: { conn: AgentConnectionCreated; onDone: () => void }) {
  const curl = `curl -X POST ${apiBase()}/drafts \\
  -H "Authorization: Bearer ${conn.api_key}" \\
  -F "image=@poster.jpg" -F "text=Details the sender typed" \\
  -F "submitted_by=+2348030000000" -F "external_id=msg-123"`;
  return (
    <div className="border-2 border-primary bg-primary/5 rounded p-4 space-y-3">
      <div>
        <p className="font-black text-text-primary">Credentials for {conn.name}</p>
        <p className="text-xs text-text-secondary">
          Copy these into the bot now. They won&apos;t be shown again (you can rotate them for new ones).
        </p>
      </div>
      {conn.api_key && <CopyField label="API key" value={conn.api_key} />}
      {conn.callback_secret && <CopyField label="Callback signing secret" value={conn.callback_secret} />}
      <CopyField label="API base URL" value={apiBase()} />
      <CopyField label="Try it: send a poster" value={curl} />
      <Button size="sm" onClick={onDone}><Check size={14} /> I&apos;ve saved them</Button>
    </div>
  );
}

function ConnectionRow({ conn, onCredentials }: { conn: AgentConnectionOut; onCredentials: (c: AgentConnectionCreated) => void }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-agent-connections"] });
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<"delete" | "rotate" | null>(null);
  const [form, setForm] = useState({
    name: conn.name, host_username: conn.host_username ?? "",
    daily_limit: String(conn.daily_limit), callback_url: conn.callback_url ?? "",
  });

  const toggle = useMutation({
    mutationFn: () => adminApi.updateAgentConnection(token!, conn.id, { is_active: !conn.is_active }),
    onSuccess: refresh,
  });
  const save = useMutation({
    mutationFn: () => adminApi.updateAgentConnection(token!, conn.id, {
      name: form.name.trim(), host_username: form.host_username.trim(),
      daily_limit: Number(form.daily_limit) || conn.daily_limit, callback_url: form.callback_url.trim(),
    }),
    onSuccess: () => { refresh(); setEditing(false); },
  });
  const rotate = useMutation({
    mutationFn: () => adminApi.rotateAgentKey(token!, conn.id),
    onSuccess: (c) => { refresh(); setConfirm(null); onCredentials(c); },
  });
  const remove = useMutation({
    mutationFn: () => adminApi.deleteAgentConnection(token!, conn.id),
    onSuccess: refresh,
  });

  if (editing) {
    return (
      <div className="border-2 border-primary bg-bg-surface shadow-brutal-sm rounded p-4 space-y-2">
        <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input label="Host account (username, optional)" value={form.host_username} placeholder="Scout bot hosts if empty"
          onChange={(e) => setForm({ ...form, host_username: e.target.value })} />
        <Input label="Daily limit" type="number" min={1} max={1000} value={form.daily_limit}
          onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} />
        <Input label="Callback URL (optional)" value={form.callback_url} placeholder="https://your-bot.example.com/turnup"
          onChange={(e) => setForm({ ...form, callback_url: e.target.value })} />
        {save.error && <p className="text-red-500 text-sm">{(save.error as Error).message}</p>}
        <div className="flex gap-2">
          <Button size="sm" loading={save.isPending} disabled={form.name.trim().length < 2} onClick={() => save.mutate()}>
            <Check size={14} /> Save
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}><XIcon size={14} /> Cancel</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-black text-text-primary truncate">{conn.name}</p>
          <p className="text-xs text-text-muted font-mono">{conn.api_key_prefix}…</p>
        </div>
        <span className={cn("shrink-0 text-xs font-bold px-2 py-0.5 rounded border-2",
          conn.is_active ? "border-green-400 text-green-700 bg-green-50" : "border-border text-text-muted bg-bg-elevated")}>
          {conn.is_active ? "active" : "paused"}
        </span>
      </div>
      <p className="text-xs text-text-muted">
        {conn.used_today}/{conn.daily_limit} today · {conn.events_created} event(s) submitted · last used {timeAgo(conn.last_used_at)}
      </p>
      <p className="text-xs text-text-muted">
        Hosted by {conn.host_username ? `@${conn.host_username}` : "the scout bot"} ·{" "}
        {conn.callback_url ? <span className="font-mono break-all">{conn.callback_url}</span> : "no callback URL (the bot polls)"}
      </p>
      {(rotate.error || remove.error || toggle.error) && (
        <p className="text-red-500 text-sm">{((rotate.error || remove.error || toggle.error) as Error).message}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}><Pencil size={14} /> Edit</Button>
        <Button size="sm" variant="secondary" loading={toggle.isPending} onClick={() => toggle.mutate()}>
          {conn.is_active ? "Pause" : "Resume"}
        </Button>
        {confirm === "rotate" ? (
          <>
            <Button size="sm" variant="danger" loading={rotate.isPending} onClick={() => rotate.mutate()}>Confirm: old key stops working</Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
          </>
        ) : confirm === "delete" ? (
          <>
            <Button size="sm" variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Confirm Delete</Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="secondary" onClick={() => setConfirm("rotate")}><KeyRound size={14} /> Rotate key</Button>
            <Button size="sm" variant="secondary" className="border-red-300 text-red-600 hover:bg-red-50" onClick={() => setConfirm("delete")}>
              Delete
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function AddConnectionForm({ onCreated }: { onCreated: (c: AgentConnectionCreated) => void }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", host_username: "", daily_limit: "", callback_url: "" });
  const create = useMutation({
    mutationFn: () => adminApi.createAgentConnection(token!, {
      name: form.name.trim(),
      host_username: form.host_username.trim() || undefined,
      daily_limit: Number(form.daily_limit) || undefined,
      callback_url: form.callback_url.trim() || undefined,
    }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["admin-agent-connections"] });
      setForm({ name: "", host_username: "", daily_limit: "", callback_url: "" });
      onCreated(c);
    },
  });
  return (
    <div className="lg:max-w-xl border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <h3 className="text-xs font-black text-text-primary uppercase tracking-widest">Connect a bot</h3>
      <Input label="Name" value={form.name} placeholder="e.g. Lagos Events WhatsApp bot"
        onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <Input label="Host account (username, optional)" value={form.host_username} placeholder="Leave empty: the scout bot hosts"
        onChange={(e) => setForm({ ...form, host_username: e.target.value })} />
      <Input label="Daily limit (optional)" type="number" min={1} max={1000} value={form.daily_limit} placeholder="50"
        onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} />
      <Input label="Callback URL (optional)" value={form.callback_url} placeholder="https://your-bot.example.com/turnup"
        onChange={(e) => setForm({ ...form, callback_url: e.target.value })} />
      <p className="text-xs text-text-muted">
        When you approve or reject one of its events, Turnup POSTs the outcome here, signed with the callback secret,
        so the bot can tell whoever sent it. Without one, the bot can poll the submission instead.
      </p>
      <Button size="sm" loading={create.isPending} disabled={form.name.trim().length < 2} onClick={() => create.mutate()}>
        Create connection
      </Button>
      {create.error && <p className="text-red-500 text-sm">{(create.error as Error).message}</p>}
    </div>
  );
}

const STATUS_LABEL: Record<AgentSubmissionOut["status"], string> = {
  created: "sent for review", skipped_duplicate: "already on Turnup", skipped_no_event: "no event found",
  failed: "failed", over_limit: "over daily limit",
};

function SubmissionLog() {
  const { token } = useAuthStore();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-agent-submissions"],
    queryFn: () => adminApi.agentSubmissions(token!, { limit: 30 }),
    enabled: !!token,
  });
  return (
    <div className="space-y-3">
      <h2 className="text-xs font-black text-text-primary uppercase tracking-widest flex items-center gap-1.5">
        <ScrollText size={12} /> Recent submissions
      </h2>
      {isLoading ? (
        <div className="animate-pulse bg-bg-elevated rounded h-24" />
      ) : data && data.length > 0 ? (
        <div className="border-2 border-border rounded divide-y-2 divide-border bg-bg-surface">
          {data.map((s) => (
            <div key={s.id} className="p-3 text-xs space-y-0.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-black text-text-primary">{s.event_title ?? (s.input_text?.slice(0, 80) || "—")}</span>
                <span className={cn("font-bold px-1.5 py-0.5 rounded border",
                  s.status === "created" ? "border-green-400 text-green-700 bg-green-50"
                    : s.status === "failed" ? "border-red-300 text-red-700 bg-red-50"
                    : "border-border text-text-muted bg-bg-elevated")}>
                  {STATUS_LABEL[s.status] ?? s.status}
                </span>
                {s.status === "created" && s.event_review_status && (
                  <span className="text-text-muted">· {s.event_review_status}</span>
                )}
              </div>
              <p className="text-text-muted">
                {s.connection_name}{s.submitted_by ? ` · from ${s.submitted_by}` : ""} · {timeAgo(s.created_at)}
              </p>
              {s.error_note && <p className="text-red-600">{s.error_note}</p>}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-center text-text-muted text-sm py-6">Nothing submitted yet.</p>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  const { token } = useAuthStore();
  const [credentials, setCredentials] = useState<AgentConnectionCreated | null>(null);
  const { data: conns, isLoading, error } = useQuery({
    queryKey: ["admin-agent-connections"],
    queryFn: () => adminApi.agentConnections(token!),
    enabled: !!token,
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Bot Connections" back />
      <div className="px-4 py-4 space-y-4 lg:max-w-4xl">
        <p className="text-xs text-text-muted">
          Let outside bots and agents (your WhatsApp or Telegram bot, an AI agent, an automation tool) send events to
          Turnup with an API key. A bot can send the details it extracted itself, or forward a poster, a link or
          pasted text and let Turnup&apos;s AI read it. Every event waits in the Events queue for your approval.
          API reference: <a className="underline" href="/api/docs#/agent%20API" target="_blank" rel="noreferrer">/api/docs</a>.
        </p>

        {credentials && <NewCredentials conn={credentials} onDone={() => setCredentials(null)} />}
        {error && <p className="text-red-500 text-sm">{(error as Error).message}</p>}

        <div className="space-y-3">
          <h2 className="text-xs font-black text-text-primary uppercase tracking-widest flex items-center gap-1.5">
            <Bot size={12} /> Connections
          </h2>
          {isLoading ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {Array.from({ length: 2 }).map((_, i) => <div key={i} className="animate-pulse bg-bg-elevated rounded h-28" />)}
            </div>
          ) : conns && conns.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {conns.map((c) => <ConnectionRow key={c.id} conn={c} onCredentials={setCredentials} />)}
            </div>
          ) : (
            <p className="text-center text-text-muted text-sm py-8">No bots connected yet. Create one below.</p>
          )}
        </div>

        <AddConnectionForm onCreated={setCredentials} />
        <SubmissionLog />
      </div>
    </div>
  );
}
