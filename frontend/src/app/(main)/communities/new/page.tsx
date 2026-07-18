"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { communitiesApi, type SocialLinks } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Lock, Globe, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";

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

const CITIES = ["Lagos", "Abuja", "Port Harcourt", "Ibadan", "Kano", "Enugu"];
const EMOJIS = ["🎵", "🎉", "🍔", "💻", "⚽", "🎨", "😂", "🌿", "🏙️", "🌊", "🔥", "✨", "🎭", "📸", "🥂"];

export default function NewCommunityPage() {
  const router = useRouter();
  const { token } = useAuthStore();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("🎉");
  const [city, setCity] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [socialLinks, setSocialLinks] = useState<SocialLinks>({});
  const [showLinks, setShowLinks] = useState(false);
  const [error, setError] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      communitiesApi.create(token!, {
        name: name.trim(),
        description: description.trim() || undefined,
        icon,
        city: city || undefined,
        is_private: isPrivate,
        social_links: socialLinks,
      }),
    onSuccess: (community) => router.replace(`/communities/${community.slug}`),
    onError: (e: any) => setError(e.message ?? "Failed to create community"),
  });

  useEffect(() => {
    if (!token) router.replace("/login");
  }, [token, router]);

  if (!token) return null;

  return (
    <div className="flex flex-col pb-8">
      <TopBar back title="New Community" />

      <div className="px-4 py-4 space-y-5">
        {/* Icon picker */}
        <div className="space-y-2">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Icon</p>
          <div className="flex flex-wrap gap-2">
            {EMOJIS.map((e) => (
              <button
                key={e}
                onClick={() => setIcon(e)}
                className={cn(
                  "w-10 h-10 rounded border-2 text-xl flex items-center justify-center transition-all",
                  icon === e
                    ? "border-primary bg-primary/10"
                    : "border-border bg-bg-card hover:border-primary/50",
                )}
              >
                {e}
              </button>
            ))}
          </div>
        </div>

        {/* Name */}
        <Input
          label="Community name *"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Lagos Afrobeats Heads"
          maxLength={100}
        />

        {/* Description */}
        <div className="space-y-1.5">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Description</p>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's this community about? Who should join?"
            rows={3}
            maxLength={2000}
            className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none"
          />
        </div>

        {/* City */}
        <div className="space-y-2">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">City (optional)</p>
          <div className="flex flex-wrap gap-2">
            {CITIES.map((c) => (
              <button
                key={c}
                onClick={() => setCity(city === c ? "" : c)}
                className={cn(
                  "px-3 py-1.5 rounded-full border-2 text-xs font-bold transition-all",
                  city === c
                    ? "bg-primary text-white border-primary"
                    : "bg-bg-surface border-border text-text-secondary hover:border-primary",
                )}
              >
                {c}
              </button>
            ))}
            <input
              type="text"
              value={CITIES.includes(city) ? "" : city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="Other city…"
              className="px-3 py-1.5 rounded border-2 border-border bg-bg-card text-xs text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
            />
          </div>
        </div>

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
                  isPrivate === value
                    ? "border-primary bg-primary/10"
                    : "border-border bg-bg-card hover:border-border-strong",
                )}
              >
                <Icon size={16} className={isPrivate === value ? "text-primary" : "text-text-muted"} />
                <p className={cn("text-sm font-bold", isPrivate === value ? "text-primary" : "text-text")}>{label}</p>
                <p className="text-xs text-text-muted">{sub}</p>
              </button>
            ))}
          </div>
        </div>

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
                  <span
                    className="w-3 h-3 rounded-full shrink-0"
                    style={{ background: color }}
                  />
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

        <Button
          fullWidth
          size="lg"
          disabled={!name.trim()}
          loading={createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          Create Community
        </Button>
      </div>
    </div>
  );
}
