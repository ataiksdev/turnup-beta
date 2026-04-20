"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { organizerApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Building2, FileText, Globe } from "lucide-react";

export default function OrganizerOnboardingPage() {
  const router = useRouter();
  const { token, setUser } = useAuthStore();

  const [form, setForm] = useState({ organization_name: "", organizer_bio: "", website: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const updated = await organizerApi.become(token, {
        organization_name: form.organization_name || undefined,
        organizer_bio: form.organizer_bio || undefined,
        website: form.website || undefined,
      });
      setUser(updated);
      router.replace("/organizer/dashboard");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleSkip() {
    if (!token) return;
    setLoading(true);
    try {
      const updated = await organizerApi.become(token, {});
      setUser(updated);
    } catch { /* swallow */ } finally {
      setLoading(false);
    }
    router.replace("/organizer/dashboard");
  }

  return (
    <div className="min-h-screen flex flex-col bg-bg px-6 py-10 safe-top">
      {/* Header */}
      <div className="space-y-2 mb-8">
        <span className="text-xs font-black text-primary uppercase tracking-widest">Step 2 of 2</span>
        <h1 className="text-3xl font-black text-text">
          Set up your <span className="text-primary">organizer</span> profile
        </h1>
        <p className="text-sm text-text-secondary">
          Tell people about yourself or your organization. You can update this anytime.
        </p>
      </div>

      {/* Organizer badge */}
      <div className="flex items-center gap-3 p-4 rounded border-2 border-primary bg-primary/10 shadow-brutal mb-8">
        <span className="text-3xl">🎤</span>
        <div>
          <p className="font-black text-primary text-sm uppercase tracking-wide">Organizer Account</p>
          <p className="text-xs text-text-muted">You can create and manage events, sell tickets, and build an audience</p>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded bg-error/10 border border-error/30 text-sm text-error mb-4">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 flex-1">
        <Input
          label="Organization / Artist Name"
          type="text"
          value={form.organization_name}
          onChange={set("organization_name")}
          placeholder="e.g. Neon Nights Events, DJ Kure"
          icon={<Building2 size={16} />}
          maxLength={200}
        />
        <Input
          label="Bio"
          type="text"
          value={form.organizer_bio}
          onChange={set("organizer_bio")}
          placeholder="A short description of what you do"
          icon={<FileText size={16} />}
          maxLength={300}
        />
        <Input
          label="Website"
          type="url"
          value={form.website}
          onChange={set("website")}
          placeholder="https://yoursite.com"
          icon={<Globe size={16} />}
        />

        <div className="pt-4 space-y-3">
          <Button type="submit" fullWidth size="lg" loading={loading}>
            Finish Setup
          </Button>
          <button
            type="button"
            onClick={handleSkip}
            disabled={loading}
            className="w-full text-sm text-text-muted text-center py-2 hover:text-text-secondary disabled:opacity-50"
          >
            Skip for now
          </button>
        </div>
      </form>
    </div>
  );
}
