"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { TopBar } from "@/components/layout/TopBar";
import { Avatar } from "@/components/ui/Avatar";
import { Lock, User, MapPin, Globe, FileText, Image } from "lucide-react";
import Link from "next/link";

export default function EditProfilePage() {
  const router = useRouter();
  const { token, user, setUser } = useAuthStore();

  const [form, setForm] = useState({
    full_name:  user?.full_name  ?? "",
    bio:        user?.bio        ?? "",
    location:   user?.location   ?? "",
    website:    user?.website    ?? "",
    avatar_url: user?.avatar_url ?? "",
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");
  const [saved,   setSaved]   = useState(false);

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setLoading(true);
    setError("");
    setSaved(false);
    try {
      const updated = await authApi.updateMe(token, {
        full_name:  form.full_name.trim()  || undefined,
        bio:        form.bio.trim()        || undefined,
        location:   form.location.trim()   || undefined,
        website:    form.website.trim()    || undefined,
        avatar_url: form.avatar_url.trim() || undefined,
      });
      setUser(updated);
      setSaved(true);
      setTimeout(() => router.replace(`/profile/${updated.username}`), 800);
    } catch (err: any) {
      setError(err.message ?? "Failed to save profile");
    } finally {
      setLoading(false);
    }
  }

  if (!user || !token) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4 px-8 text-center">
        <Lock size={48} className="text-primary" aria-hidden />
        <p className="text-text-secondary font-bold text-sm uppercase tracking-wide">Sign in to edit your profile</p>
        <Link href="/login"><Button>Log In</Button></Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <TopBar back title="Edit Profile" />

      <div className="px-4 py-6 space-y-6">
        {/* Avatar preview */}
        <div className="flex flex-col items-center gap-3">
          <div className="border-4 border-border rounded-full shadow-brutal">
            <Avatar
              src={form.avatar_url || user.avatar_url}
              name={form.full_name || user.full_name}
              size="xl"
              verified={user.is_verified}
            />
          </div>
          <p className="text-xs font-bold text-text-muted uppercase tracking-widest">
            @{user.username}
          </p>
        </div>

        {/* Status messages */}
        {error && (
          <div className="px-4 py-3 rounded border-2 border-error/30 bg-error/10 text-sm text-error">
            {error}
          </div>
        )}
        {saved && (
          <div className="px-4 py-3 rounded border-2 border-success/30 bg-success/10 text-sm text-success font-bold">
            ✓ Profile saved
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Full Name"
            type="text"
            value={form.full_name}
            onChange={set("full_name")}
            placeholder="Your name"
            icon={<User size={16} />}
            maxLength={120}
          />

          {/* Bio — textarea */}
          <div className="space-y-1">
            <p className="text-[10px] font-black text-text-muted uppercase tracking-widest mb-1.5">
              Bio <span className="normal-case text-text-disabled">({form.bio.length}/500)</span>
            </p>
            <textarea
              value={form.bio}
              onChange={set("bio")}
              placeholder="A short bio about yourself…"
              rows={3}
              maxLength={500}
              className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none transition-all"
            />
          </div>

          <Input
            label="Location"
            type="text"
            value={form.location}
            onChange={set("location")}
            placeholder="e.g. Lagos, Nigeria"
            icon={<MapPin size={16} />}
            maxLength={120}
          />

          <Input
            label="Website"
            type="url"
            value={form.website}
            onChange={set("website")}
            placeholder="https://yoursite.com"
            icon={<Globe size={16} />}
            maxLength={255}
          />

          <div className="space-y-1">
            <Input
              label="Avatar URL"
              type="url"
              value={form.avatar_url}
              onChange={set("avatar_url")}
              placeholder="https://..."
              icon={<Image size={16} />}
            />
            <p className="text-[10px] text-text-muted">Paste a direct image URL. Upload support coming soon.</p>
          </div>

          <div className="pt-2 space-y-3">
            <Button type="submit" fullWidth size="lg" loading={loading}>
              Save Profile
            </Button>
            <Button type="button" variant="secondary" fullWidth size="lg" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
