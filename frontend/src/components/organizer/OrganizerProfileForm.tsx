"use client";
import { useState } from "react";
import { Building2, Globe } from "lucide-react";
import { authApi, organizerApi, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

/** Edit the organizer-facing details shown on your profile and checked during verification. */
export function OrganizerProfileForm() {
  const { token, user, setUser } = useAuthStore();
  const p = user?.organizer_profile;
  const [orgName, setOrgName] = useState(p?.organization_name ?? "");
  const [bio, setBio] = useState(p?.organizer_bio ?? "");
  const [website, setWebsite] = useState(p?.website ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  if (!user || user.role !== "organizer") return null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setMessage(null);
    try {
      await organizerApi.updateProfile(token, {
        organization_name: orgName.trim(), organizer_bio: bio.trim(), website: website.trim(),
      });
      setUser(await authApi.me(token));
      setMessage({ ok: true, text: "Saved." });
    } catch (err) {
      setMessage({ ok: false, text: apiErrorMessage(err, "Could not save your organizer profile.") });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="p-4 rounded border-2 border-border bg-bg-card space-y-3">
      <p className="text-xs font-black uppercase tracking-widest text-text-muted">Organizer profile</p>
      <Input label="Organization name" value={orgName} maxLength={200}
        onChange={(e) => setOrgName(e.target.value)} icon={<Building2 size={16} />} />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="org-bio" className="text-xs font-bold text-text-secondary uppercase tracking-wide">About you as an organizer</label>
        <textarea id="org-bio" value={bio} maxLength={1000} rows={3} onChange={(e) => setBio(e.target.value)}
          className="w-full rounded border-2 border-border bg-bg px-3 py-2 text-sm text-text focus:outline-none focus:border-primary" />
      </div>
      <Input label="Website" type="url" value={website} placeholder="https://..."
        onChange={(e) => setWebsite(e.target.value)} icon={<Globe size={16} />} />
      {message && <p role="status" className={message.ok ? "text-xs text-success" : "text-xs text-error"}>{message.text}</p>}
      <Button type="submit" size="sm" loading={saving}>Save organizer profile</Button>
    </form>
  );
}
