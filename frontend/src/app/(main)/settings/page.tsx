"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Laptop, Lock, LogOut, Mail, ShieldCheck, Trash2, AlertTriangle } from "lucide-react";
import { authApi, type SessionInfo } from "@/lib/api";
import { useLogout } from "@/lib/session";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/layout/AuthShell";
import { timeAgo } from "@/lib/utils";
import { AppearanceSettings } from "@/components/settings/AppearanceSettings";

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="border-2 border-border rounded bg-bg-card p-4 space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-text">
        {icon} {title}
      </h2>
      {children}
    </section>
  );
}

function msg(err: unknown, fallback: string) {
  return (err as { message?: string })?.message ?? fallback;
}

// ── Email ───────────────────────────────────────────────────────────────────────
function EmailSection() {
  const { token, user } = useAuthStore();
  const resend = useMutation({ mutationFn: () => authApi.resendVerification(token!) });
  if (!user) return null;
  return (
    <Section icon={<Mail size={16} />} title="Email">
      {user.email ? (
        <>
          <p className="text-sm text-text flex items-center gap-2 flex-wrap">
            {user.email}
            {user.email_verified ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-success">
                <CheckCircle2 size={12} /> Verified
              </span>
            ) : (
              <span className="text-xs font-bold text-warning">Not verified</span>
            )}
          </p>
          {!user.email_verified && (
            resend.isSuccess ? (
              <Notice tone="success">Verification email sent. Check your inbox.</Notice>
            ) : (
              <>
                {resend.isError && <Notice tone="error">{msg(resend.error, "Could not send the email.")}</Notice>}
                <Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
                  Resend verification email
                </Button>
              </>
            )
          )}
        </>
      ) : (
        <p className="text-sm text-text-muted">No email on this account (you sign in with your phone).</p>
      )}
    </Section>
  );
}

// ── Password ────────────────────────────────────────────────────────────────────
function PasswordSection() {
  const { token, user } = useAuthStore();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState("");
  const change = useMutation({
    mutationFn: () => authApi.changePassword(token!, current, next),
    onSuccess: () => { setCurrent(""); setNext(""); setConfirm(""); },
  });
  if (!user) return null;

  if (!user.has_password) {
    return (
      <Section icon={<Lock size={16} />} title="Password">
        <p className="text-sm text-text-muted">
          You sign in without a password (Google, Instagram, phone or email link).
          {user.email && (
            <> To add one, use{" "}
              <Link href="/forgot-password" className="text-primary font-medium hover:underline">reset password</Link>{" "}
              with {user.email}.
            </>
          )}
        </p>
      </Section>
    );
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (next.length < 8) return setLocalError("Use at least 8 characters.");
    if (next !== confirm) return setLocalError("The new passwords don't match.");
    change.mutate();
  }

  return (
    <Section icon={<Lock size={16} />} title="Password">
      <form onSubmit={submit} className="space-y-3">
        {(localError || change.isError) && (
          <Notice tone="error">{localError || msg(change.error, "Could not change password.")}</Notice>
        )}
        {change.isSuccess && <Notice tone="success">{change.data.message}</Notice>}
        <Input label="Current password" type="password" autoComplete="current-password"
          value={current} onChange={(e) => setCurrent(e.target.value)} required />
        <Input label="New password" type="password" autoComplete="new-password"
          value={next} onChange={(e) => setNext(e.target.value)} placeholder="At least 8 characters" required />
        <Input label="Confirm new password" type="password" autoComplete="new-password"
          value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        <Button type="submit" size="sm" loading={change.isPending}>Change password</Button>
      </form>
    </Section>
  );
}

// ── Two-factor ──────────────────────────────────────────────────────────────────
function BackupCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  return (
    <div className="space-y-3">
      <Notice tone="info">
        Save these backup codes somewhere safe. Each works once if you lose your phone.
        They won&apos;t be shown again.
      </Notice>
      <ul className="grid grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((c) => <li key={c} className="border-2 border-border rounded px-2 py-1 text-center">{c}</li>)}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => navigator.clipboard?.writeText(codes.join("\n"))}>
          Copy codes
        </Button>
        <Button size="sm" onClick={onDone}>I&apos;ve saved them</Button>
      </div>
    </div>
  );
}

function TwoFactorSection() {
  const { token, user, setUser } = useAuthStore();
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [mode, setMode] = useState<"idle" | "disable" | "regenerate">("idle");

  const refreshUser = async () => { if (token) setUser(await authApi.me(token)); };
  const setup = useMutation({ mutationFn: () => authApi.setup2fa(token!) });
  const enable = useMutation({
    mutationFn: () => authApi.enable2fa(token!, code.trim()),
    onSuccess: async (r) => { setBackupCodes(r.backup_codes); setCode(""); setup.reset(); await refreshUser(); },
  });
  const disable = useMutation({
    mutationFn: () => authApi.disable2fa(token!, code.trim()),
    onSuccess: async () => { setCode(""); setMode("idle"); await refreshUser(); },
  });
  const regenerate = useMutation({
    mutationFn: () => authApi.regenerateBackupCodes(token!, code.trim()),
    onSuccess: (r) => { setBackupCodes(r.backup_codes); setCode(""); setMode("idle"); },
  });
  if (!user) return null;

  const title = "Two-factor authentication";
  if (backupCodes) {
    return (
      <Section icon={<ShieldCheck size={16} />} title={title}>
        <BackupCodes codes={backupCodes} onDone={() => setBackupCodes(null)} />
      </Section>
    );
  }

  if (!user.has_password) {
    return (
      <Section icon={<ShieldCheck size={16} />} title={title}>
        <p className="text-sm text-text-muted">
          Two-factor protects password and email-link sign-in. Add a password to your account first.
        </p>
      </Section>
    );
  }

  if (user.two_factor_enabled) {
    const busy = disable.isPending || regenerate.isPending;
    const err = disable.error || regenerate.error;
    return (
      <Section icon={<ShieldCheck size={16} />} title={title}>
        <p className="text-sm text-success font-bold flex items-center gap-1">
          <CheckCircle2 size={14} /> On: you&apos;ll be asked for a code when you sign in.
        </p>
        {mode === "idle" ? (
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="secondary" onClick={() => setMode("regenerate")}>New backup codes</Button>
            <Button size="sm" variant="danger" onClick={() => setMode("disable")}>Turn off</Button>
          </div>
        ) : (
          <form
            onSubmit={(e) => { e.preventDefault(); (mode === "disable" ? disable : regenerate).mutate(); }}
            className="space-y-3"
          >
            {err && <Notice tone="error">{msg(err, "Invalid code")}</Notice>}
            <Input
              label={mode === "disable" ? "Code (or a backup code) to confirm" : "Code from your authenticator app"}
              autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.slice(0, 9))} required
            />
            <div className="flex gap-2">
              <Button type="submit" size="sm" variant={mode === "disable" ? "danger" : "primary"} loading={busy}>
                {mode === "disable" ? "Turn off 2FA" : "Generate codes"}
              </Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => { setMode("idle"); setCode(""); }}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </Section>
    );
  }

  return (
    <Section icon={<ShieldCheck size={16} />} title={title}>
      {!setup.data ? (
        <>
          <p className="text-sm text-text-muted">
            Add a second step to sign-in using an authenticator app (Google Authenticator, 1Password, Authy…).
          </p>
          {setup.isError && <Notice tone="error">{msg(setup.error, "Could not start setup.")}</Notice>}
          <Button size="sm" loading={setup.isPending} onClick={() => setup.mutate()}>Set up 2FA</Button>
        </>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); enable.mutate(); }} className="space-y-3">
          <p className="text-sm text-text">1. Scan this QR code with your authenticator app.</p>
          {/* Rendered as an <img>, not injected HTML: the SVG comes from our API, but an image
              context can't run script even if that ever changed. */}
          <img
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(setup.data.qr_svg)}`}
            alt="QR code for your authenticator app"
            className="w-44 h-44 bg-white p-2 rounded border-2 border-border"
          />
          <p className="text-xs text-text-muted break-all">
            Can&apos;t scan? Enter this key: <span className="font-mono text-text">{setup.data.secret}</span>
          </p>
          <p className="text-sm text-text">2. Enter the 6-digit code it shows.</p>
          {enable.isError && <Notice tone="error">{msg(enable.error, "Invalid code")}</Notice>}
          <Input label="Code" inputMode="numeric" autoComplete="one-time-code"
            value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} required />
          <Button type="submit" size="sm" loading={enable.isPending}>Turn on 2FA</Button>
        </form>
      )}
    </Section>
  );
}

// ── Sessions ────────────────────────────────────────────────────────────────────
function describeDevice(s: SessionInfo) {
  if (s.device_name) return s.device_name;
  const ua = s.user_agent ?? "";
  const os = /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iOS"
    : /Mac OS/i.test(ua) ? "macOS" : /Windows/i.test(ua) ? "Windows" : /Linux/i.test(ua) ? "Linux" : "Unknown device";
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox"
    : /Safari\//.test(ua) ? "Safari" : "";
  return browser ? `${browser} on ${os}` : os;
}

function SessionsSection() {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions"], queryFn: () => authApi.sessions(token!), enabled: !!token,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => authApi.revokeSession(token!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const revokeOthers = useMutation({
    mutationFn: () => authApi.revokeOtherSessions(token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  return (
    <Section icon={<Laptop size={16} />} title="Where you're signed in">
      {isLoading && <p className="text-sm text-text-muted">Loading…</p>}
      <ul className="divide-y-2 divide-border">
        {sessions?.map((s) => (
          <li key={s.id} className="py-2 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-bold text-text truncate">
                {describeDevice(s)}
                {s.is_current && <span className="ml-2 text-xs text-success">This device</span>}
              </p>
              <p className="text-xs text-text-muted">
                {s.ip_address ?? "Unknown IP"} · signed in {timeAgo(s.created_at)}
              </p>
            </div>
            {!s.is_current && (
              <Button size="xs" variant="secondary" loading={revoke.isPending && revoke.variables === s.id}
                onClick={() => revoke.mutate(s.id)}>
                Sign out
              </Button>
            )}
          </li>
        ))}
      </ul>
      {revokeOthers.isSuccess && <Notice tone="success">{revokeOthers.data.message}</Notice>}
      {sessions && sessions.length > 1 && (
        <Button size="sm" variant="secondary" loading={revokeOthers.isPending} onClick={() => revokeOthers.mutate()}>
          Sign out of all other devices
        </Button>
      )}
    </Section>
  );
}

// ── Delete account ──────────────────────────────────────────────────────────────
function DeleteSection() {
  const { token, user, logout } = useAuthStore();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const del = useMutation({
    mutationFn: () => authApi.deleteAccount(token!, user?.has_password
      ? { password: value } : { confirm_username: value }),
    onSuccess: () => { logout(); window.location.replace("/"); },
  });
  if (!user) return null;
  return (
    <Section icon={<Trash2 size={16} />} title="Delete account">
      {!open ? (
        <>
          <p className="text-sm text-text-muted">
            Permanently deactivate your account and sign out everywhere. Tickets you&apos;ve bought stay valid
            for check-in but you won&apos;t be able to see them here.
          </p>
          <Button size="sm" variant="danger" onClick={() => setOpen(true)}>Delete my account</Button>
        </>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); del.mutate(); }} className="space-y-3">
          <Notice tone="error">
            <span className="flex items-center gap-2 font-bold"><AlertTriangle size={14} /> This can&apos;t be undone.</span>
          </Notice>
          {del.isError && <Notice tone="error">{msg(del.error, "Could not delete account.")}</Notice>}
          <Input
            label={user.has_password ? "Your password" : `Type your username (${user.username}) to confirm`}
            type={user.has_password ? "password" : "text"}
            value={value} onChange={(e) => setValue(e.target.value)} required
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" variant="danger" loading={del.isPending}>Delete permanently</Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => { setOpen(false); setValue(""); }}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Section>
  );
}

export default function SettingsPage() {
  const { token, user, hasHydrated } = useAuthStore();
  const logoutEverywhere = useLogout();

  if (hasHydrated && (!token || !user)) {
    return (
      <div className="flex flex-col pb-8">
        <TopBar title="Settings" back />
        <div className="px-4 pt-4 space-y-4 max-w-2xl w-full mx-auto">
          <AppearanceSettings />
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <KeyRound size={36} className="text-primary" aria-hidden />
            <p className="text-sm text-text-secondary">Log in to manage your account, and to keep your theme on every device.</p>
            <Link href="/login?next=/settings"><Button>Log In</Button></Link>
          </div>
        </div>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="flex flex-col pb-8">
      <TopBar title="Settings" back />
      <div className="px-4 pt-4 space-y-4 max-w-2xl w-full mx-auto">
        <AppearanceSettings />
        <EmailSection />
        <PasswordSection />
        <TwoFactorSection />
        <SessionsSection />
        <Button variant="secondary" fullWidth onClick={logoutEverywhere}>
          <LogOut size={16} /> Log out
        </Button>
        <DeleteSection />
      </div>
    </div>
  );
}
