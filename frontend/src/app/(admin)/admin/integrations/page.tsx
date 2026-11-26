"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AgentConnectionOut, AgentConnectionCreated, AgentSubmissionOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Bot, Copy, Check, KeyRound, Pencil, X as XIcon, ScrollText, Send, Plug } from "lucide-react";
import { cn } from "@/lib/utils";

type Kind = "telegram" | "api";

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

/** API connections, right after creating or rotating: the only time the key and secret show. */
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
          Copy these into the program now. They won&apos;t be shown again (rotate the key for new ones).
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

function StatusPill({ conn }: { conn: AgentConnectionOut }) {
  const [label, cls] = !conn.is_active
    ? ["paused", "border-border text-text-muted bg-bg-elevated"]
    : conn.kind === "telegram" && !conn.telegram_connected
      ? ["not connected", "border-yellow-400 text-yellow-700 bg-yellow-50"]
      : ["active", "border-green-400 text-green-700 bg-green-50"];
  return <span className={cn("shrink-0 text-xs font-bold px-2 py-0.5 rounded border-2", cls)}>{label}</span>;
}

function ConnectionRow({ conn, onCredentials }: { conn: AgentConnectionOut; onCredentials: (c: AgentConnectionCreated) => void }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-agent-connections"] });
  const isTelegram = conn.kind === "telegram";
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<"delete" | "rotate" | null>(null);
  const [form, setForm] = useState({
    name: conn.name, host_username: conn.host_username ?? "", daily_limit: String(conn.daily_limit),
    callback_url: conn.callback_url ?? "", allowed_senders: conn.allowed_senders ?? "", telegram_bot_token: "",
  });

  const toggle = useMutation({
    mutationFn: () => adminApi.updateAgentConnection(token!, conn.id, { is_active: !conn.is_active }),
    onSuccess: refresh,
  });
  const save = useMutation({
    mutationFn: () => adminApi.updateAgentConnection(token!, conn.id, {
      name: form.name.trim(), host_username: form.host_username.trim(),
      daily_limit: Number(form.daily_limit) || conn.daily_limit,
      ...(isTelegram
        ? { allowed_senders: form.allowed_senders, ...(form.telegram_bot_token.trim() ? { telegram_bot_token: form.telegram_bot_token.trim() } : {}) }
        : { callback_url: form.callback_url.trim() }),
    }),
    onSuccess: () => { refresh(); setEditing(false); setForm((f) => ({ ...f, telegram_bot_token: "" })); },
  });
  const connect = useMutation({
    mutationFn: () => adminApi.connectTelegram(token!, conn.id),
    onSuccess: refresh,
  });
  const rotate = useMutation({
    mutationFn: () => adminApi.rotateAgentKey(token!, conn.id),
    onSuccess: (c) => { refresh(); setConfirm(null); onCredentials(c); },
  });
  const remove = useMutation({
    mutationFn: () => adminApi.deleteAgentConnection(token!, conn.id),
    onSuccess: refresh,
  });
  const anyError = (save.error || connect.error || rotate.error || remove.error || toggle.error) as Error | null;

  if (editing) {
    return (
      <div className="border-2 border-primary bg-bg-surface shadow-brutal-sm rounded p-4 space-y-2">
        <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        {isTelegram ? (
          <>
            <Input label="Allowed Telegram user ids" value={form.allowed_senders} placeholder="e.g. 111222333, 444555666"
              onChange={(e) => setForm({ ...form, allowed_senders: e.target.value })} />
            <Input label="New bot token (optional)" type="password" value={form.telegram_bot_token}
              placeholder="Leave empty to keep the current bot"
              onChange={(e) => setForm({ ...form, telegram_bot_token: e.target.value })} />
          </>
        ) : (
          <Input label="Callback URL (optional)" value={form.callback_url} placeholder="https://your-bot.example.com/turnup"
            onChange={(e) => setForm({ ...form, callback_url: e.target.value })} />
        )}
        <Input label="Host account (username, optional)" value={form.host_username} placeholder="Scout bot hosts if empty"
          onChange={(e) => setForm({ ...form, host_username: e.target.value })} />
        <Input label="Daily limit" type="number" min={1} max={1000} value={form.daily_limit}
          onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} />
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
          <p className="font-black text-text-primary truncate flex items-center gap-1.5">
            {isTelegram ? <Send size={14} aria-hidden /> : <KeyRound size={14} aria-hidden />} {conn.name}
          </p>
          <p className="text-xs text-text-muted font-mono">
            {isTelegram
              ? (conn.telegram_bot_username ? `@${conn.telegram_bot_username}` : "Telegram bot")
              : `${conn.api_key_prefix}…`}
          </p>
        </div>
        <StatusPill conn={conn} />
      </div>

      {isTelegram && !conn.telegram_connected && (
        <p className="text-xs text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-2 py-1.5">
          Press Connect so Telegram sends the bot&apos;s messages to Turnup.
        </p>
      )}
      {isTelegram && !conn.allowed_senders && (
        <p className="text-xs text-yellow-800 bg-yellow-50 border border-yellow-200 rounded px-2 py-1.5">
          Nobody is allowed to submit yet. Message the bot <span className="font-mono">/whoami</span>, then add that id with Edit.
        </p>
      )}

      <p className="text-xs text-text-muted">
        {conn.used_today}/{conn.daily_limit} today · {conn.events_created} event(s) submitted · last used {timeAgo(conn.last_used_at)}
      </p>
      <p className="text-xs text-text-muted">
        Hosted by {conn.host_username ? `@${conn.host_username}` : "the scout bot"} ·{" "}
        {isTelegram
          ? <>allowed: {conn.allowed_senders ? <span className="font-mono">{conn.allowed_senders}</span> : "nobody"}</>
          : conn.callback_url ? <span className="font-mono break-all">{conn.callback_url}</span> : "no callback URL (it polls)"}
      </p>
      {anyError && <p className="text-red-500 text-sm">{anyError.message}</p>}

      <div className="flex flex-wrap gap-2">
        {isTelegram && (
          <Button size="sm" variant={conn.telegram_connected ? "secondary" : "primary"} loading={connect.isPending} onClick={() => connect.mutate()}>
            <Plug size={14} /> {conn.telegram_connected ? "Reconnect" : "Connect"}
          </Button>
        )}
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
            {!isTelegram && (
              <Button size="sm" variant="secondary" onClick={() => setConfirm("rotate")}><KeyRound size={14} /> Rotate key</Button>
            )}
            <Button size="sm" variant="secondary" className="border-red-300 text-red-600 hover:bg-red-50" onClick={() => setConfirm("delete")}>
              Delete
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

const EMPTY = { name: "", host_username: "", daily_limit: "", callback_url: "", telegram_bot_token: "", allowed_senders: "" };

function AddConnectionForm({ onCreated }: { onCreated: (c: AgentConnectionCreated) => void }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>("telegram");
  const [form, setForm] = useState(EMPTY);
  const create = useMutation({
    mutationFn: () => adminApi.createAgentConnection(token!, {
      name: form.name.trim(), kind,
      host_username: form.host_username.trim() || undefined,
      daily_limit: Number(form.daily_limit) || undefined,
      ...(kind === "telegram"
        ? { telegram_bot_token: form.telegram_bot_token.trim(), allowed_senders: form.allowed_senders }
        : { callback_url: form.callback_url.trim() || undefined }),
    }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["admin-agent-connections"] });
      setForm(EMPTY);
      if (c.api_key) onCreated(c);
    },
  });
  const ready = form.name.trim().length >= 2 && (kind === "api" || !!form.telegram_bot_token.trim());

  return (
    <div className="lg:max-w-xl border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <h3 className="text-xs font-black text-text-primary uppercase tracking-widest">Connect a bot</h3>
      <div className="flex gap-2" role="radiogroup" aria-label="Connection type">
        {([["telegram", "Telegram bot", Send], ["api", "API key", KeyRound]] as const).map(([k, label, Icon]) => (
          <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
            className={cn("flex-1 flex items-center justify-center gap-1.5 h-9 rounded border-2 text-sm font-bold",
              kind === k ? "border-primary bg-primary text-on-primary" : "border-border text-text-secondary hover:bg-bg-elevated")}>
            <Icon size={14} aria-hidden /> {label}
          </button>
        ))}
      </div>

      {kind === "telegram" ? (
        <>
          <p className="text-xs text-text-muted">
            Turnup runs the bot. Make one with <span className="font-mono">@BotFather</span> on Telegram
            (<span className="font-mono">/newbot</span>) and paste the token it gives you. People on the
            allowlist DM it a poster, a link or the details; everyone else is told it isn&apos;t open yet.
          </p>
          <Input label="Name" value={form.name} placeholder="e.g. Turnup events bot"
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Bot token" type="password" value={form.telegram_bot_token} placeholder="123456789:AA..."
            onChange={(e) => setForm({ ...form, telegram_bot_token: e.target.value })} />
          <Input label="Allowed Telegram user ids (optional now)" value={form.allowed_senders} placeholder="Message the bot /whoami to get yours"
            onChange={(e) => setForm({ ...form, allowed_senders: e.target.value })} />
        </>
      ) : (
        <>
          <p className="text-xs text-text-muted">
            For an outside program (an AI agent, n8n, a partner&apos;s bot) that calls Turnup&apos;s API.
            You&apos;ll get a key to give it.
          </p>
          <Input label="Name" value={form.name} placeholder="e.g. Partner agent"
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Callback URL (optional)" value={form.callback_url} placeholder="https://your-bot.example.com/turnup"
            onChange={(e) => setForm({ ...form, callback_url: e.target.value })} />
        </>
      )}
      <Input label="Daily limit (optional)" type="number" min={1} max={1000} value={form.daily_limit} placeholder="50"
        onChange={(e) => setForm({ ...form, daily_limit: e.target.value })} />
      <Button size="sm" loading={create.isPending} disabled={!ready} onClick={() => create.mutate()}>
        Create connection
      </Button>
      {create.error && <p className="text-red-500 text-sm">{(create.error as Error).message}</p>}
    </div>
  );
}

const STATUS_LABEL: Record<AgentSubmissionOut["status"], string> = {
  created: "sent for review", skipped_duplicate: "already on Turnup", skipped_no_event: "no event found",
  failed: "failed", over_limit: "over daily limit", sender_not_allowed: "not on allowlist",
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
          Send events to Turnup from outside the app: DM a poster, a link or the details to Turnup&apos;s
          Telegram bot, or let an outside program use an API key. The AI reads each one and it waits in the
          Events queue for your approval; the sender hears back when you approve or reject it.
          Guide: <span className="font-mono">docs/agent-connections.md</span>.
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
            <p className="text-center text-text-muted text-sm py-8">Nothing connected yet. Create one below.</p>
          )}
        </div>

        <AddConnectionForm onCreated={setCredentials} />
        <SubmissionLog />
      </div>
    </div>
  );
}
