"use client";
import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { communitiesApi, type SocialLinks } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Globe, Lock, ChevronDown, ChevronUp, RefreshCw, Trash2, Copy, Check } from "lucide-react";
import { cn, copyToClipboard } from "@/lib/utils";

const PLATFORM_META: { key: keyof SocialLinks; label: string; placeholder: string; color: string }[] = [
  { key: "whatsapp",  label: "WhatsApp",  placeholder: "https://chat.whatsapp.com/...", color: "#25D366" },
  { key: "instagram", label: "Instagram", placeholder: "https://instagram.com/...",     color: "#E1306C" },
  { key: "discord",   label: "Discord",   placeholder: "https://discord.gg/...",        color: "#5865F2" },
  { key: "telegram",  label: "Telegram",  placeholder: "https://t.me/...",             color: "#2AABEE" },
  { key: "twitter",   label: "Twitter/X", placeholder: "https://x.com/...",            color: "#000000" },
  { key: "facebook",  label: "Facebook",  placeholder: "https://facebook.com/...",      color: "#1877F2" },
  { key: "tiktok",    label: "TikTok",    placeholder: "https://tiktok.com/@...",       color: "#010101" },
  { key: "youtube",   label: "YouTube",   placeholder: "https://youtube.com/...",       color: "#FF0000" },
  { key: "website",   label: "Website",   placeholder: "https://...",                   color: "#6B7280" },
];

export default function CommunitySettingsPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { token } = useAuthStore();
  const qc = useQueryClient();

  const { data: community, isLoading } = useQuery({
    queryKey: ["community", slug],
    queryFn: () => communitiesApi.get(slug, token ?? undefined),
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [socialLinks, setSocialLinks] = useState<SocialLinks>({});
  const [showLinks, setShowLinks] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (community) {
      setName(community.name);
      setDescription(community.description ?? "");
      setCity(community.city ?? "");
      setIsPrivate(community.is_private);
      setSocialLinks(community.social_links as SocialLinks ?? {});
    }
  }, [community]);

  const updateMutation = useMutation({
    mutationFn: () => communitiesApi.update(token!, slug, {
      name: name.trim(),
      description: description.trim() || undefined,
      city: city || undefined,
      is_private: isPrivate,
      social_links: socialLinks,
    }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["community", slug] });
      router.replace(`/communities/${updated.slug}`);
    },
    onError: (e: any) => setError(e.message ?? "Update failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => communitiesApi.delete(token!, slug),
    onSuccess: () => router.replace("/communities"),
  });

  const regenMutation = useMutation({
    mutationFn: () => communitiesApi.regenerateInvite(token!, slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["community", slug] }),
  });

  function copyInviteLink() {
    if (!community?.invite_token) return;
    copyToClipboard(`${window.location.origin}/communities/join/${community.invite_token}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) return <div className="flex flex-col"><TopBar back title="Settings" /></div>;
  if (!community || community.member_role !== "admin") {
    router.replace(`/communities/${slug}`);
    return null;
  }

  return (
    <div className="flex flex-col pb-8">
      <TopBar back title="Community Settings" />

      <div className="px-4 py-4 space-y-5">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />

        <div className="space-y-1.5">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Description</p>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            maxLength={2000}
            className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none"
          />
        </div>

        <Input label="City" value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Lagos" />

        {/* Privacy */}
        <div className="space-y-2">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Privacy</p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { value: false, label: "Public", icon: Globe, sub: "Anyone can join" },
              { value: true,  label: "Private", icon: Lock, sub: "Invite link only" },
            ].map(({ value, label, icon: Icon, sub }) => (
              <button
                key={String(value)}
                onClick={() => setIsPrivate(value)}
                className={cn(
                  "flex flex-col items-start gap-1 p-3 rounded border-2 text-left transition-all",
                  isPrivate === value ? "border-primary bg-primary/10" : "border-border bg-bg-card hover:border-border-strong",
                )}
              >
                <Icon size={16} className={isPrivate === value ? "text-primary" : "text-text-muted"} />
                <p className={cn("text-sm font-bold", isPrivate === value ? "text-primary" : "text-text")}>{label}</p>
                <p className="text-xs text-text-muted">{sub}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Invite link management */}
        {isPrivate && community.invite_token && (
          <div className="p-4 rounded border-2 border-border bg-bg-card space-y-3">
            <p className="text-xs font-black text-text-muted uppercase tracking-widest">Invite Link</p>
            <p className="text-xs text-text-secondary break-all font-mono bg-bg-elevated px-2 py-1.5 rounded">
              {`${typeof window !== "undefined" ? window.location.origin : ""}/communities/join/${community.invite_token}`}
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={copyInviteLink}>
                {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
                {copied ? "Copied!" : "Copy"}
              </Button>
              <Button size="sm" variant="ghost" loading={regenMutation.isPending} onClick={() => regenMutation.mutate()}>
                <RefreshCw size={13} /> New link
              </Button>
            </div>
          </div>
        )}

        {/* Social links */}
        <div className="space-y-2">
          <button
            onClick={() => setShowLinks((v) => !v)}
            className="flex items-center gap-2 text-xs font-black text-text-muted uppercase tracking-widest hover:text-text transition-colors"
          >
            {showLinks ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            Social links & chat portals
          </button>
          {showLinks && (
            <div className="space-y-2 pl-1">
              {PLATFORM_META.map(({ key, label, placeholder, color }) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ background: color }} />
                  <input
                    type="url"
                    placeholder={`${label}: ${placeholder}`}
                    value={(socialLinks[key] as string) ?? ""}
                    onChange={(e) => setSocialLinks((prev) => ({ ...prev, [key]: e.target.value || undefined }))}
                    className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2 text-xs text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {error && <p className="text-sm text-error">{error}</p>}

        <Button fullWidth size="lg" loading={updateMutation.isPending} onClick={() => updateMutation.mutate()}>
          Save Changes
        </Button>

        {/* Danger zone */}
        <div className="mt-6 p-4 rounded border-2 border-error/30 bg-error/5 space-y-3">
          <p className="text-xs font-black text-error uppercase tracking-widest">Danger Zone</p>
          <p className="text-xs text-text-muted">Deleting this community is permanent and cannot be undone.</p>
          {!confirmDelete ? (
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={14} /> Delete Community
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="danger" size="sm" loading={deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
                Yes, delete
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
