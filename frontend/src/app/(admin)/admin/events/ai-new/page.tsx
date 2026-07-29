"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { adminApi, eventsApi, AIEventDraft } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { TopBar } from "@/components/layout/TopBar";
import { cn } from "@/lib/utils";
import { Link2, ImageIcon, Sparkles, X, FileText } from "lucide-react";
import { AI_DRAFT_SESSION_KEY } from "@/lib/aiDraft";

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-black text-text-muted uppercase tracking-widest mb-1.5">{children}</p>;
}

function FieldWrap({ children }: { children: React.ReactNode }) {
  return <div className="space-y-1">{children}</div>;
}

// Converts an ISO datetime string to the "YYYY-MM-DDTHH:mm" shape <input type="datetime-local"> expects.
function isoToLocalInput(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function AIDraftEventPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<AIEventDraft | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => eventsApi.categories(),
  });

  function handleImageChange(file: File | null) {
    setImage(file);
    setImagePreview(file ? URL.createObjectURL(file) : null);
  }

  async function generate() {
    if (!text.trim() && !url.trim() && !image) {
      setError("Add a description, a URL, or a flyer image to draft from.");
      return;
    }
    if (!token) return;
    setLoading(true);
    setError("");
    setDraft(null);
    try {
      const result = await adminApi.draftEvent(token, {
        text: text.trim() || undefined,
        url: url.trim() || undefined,
        image: image ?? undefined,
      });
      setDraft(result);
    } catch (e: any) {
      setError(e.message ?? "AI drafting failed");
    } finally {
      setLoading(false);
    }
  }

  function useDraft() {
    if (!draft) return;
    const matchedCategory = categories?.find(
      (c) => c.name.toLowerCase() === draft.category_guess.toLowerCase(),
    );
    const prefill = {
      title: draft.title,
      description: draft.description,
      cover_image: draft.cover_image || "",
      venue_name: draft.venue_name,
      address: draft.address,
      city: draft.city,
      country: draft.country || "Nigeria",
      start_date: draft.start_date ? isoToLocalInput(draft.start_date) : "",
      end_date: draft.end_date ? isoToLocalInput(draft.end_date) : "",
      is_free: draft.is_free,
      price_min: draft.price_min != null ? String(draft.price_min) : "",
      price_max: draft.price_max != null ? String(draft.price_max) : "",
      currency: draft.currency || "NGN",
      event_type: draft.event_type,
      category_id: matchedCategory?.id ?? "",
      tags: draft.tags,
    };
    sessionStorage.setItem(AI_DRAFT_SESSION_KEY, JSON.stringify(prefill));
    router.push("/admin/events/new");
  }

  return (
    <div className="flex flex-col pb-24">
      <TopBar title="AI Draft Event" back />

      <div className="px-4 py-4 lg:flex lg:gap-6 lg:items-start lg:max-w-5xl">
        <div className="space-y-5 lg:flex-1 lg:max-w-xl">
        <p className="text-xs text-text-muted">
          Paste a description, drop in a source URL, and/or upload a flyer image — Claude will
          draft the event fields for you to review and edit before submitting.
        </p>

        <FieldWrap>
          <Label>Pasted Description</Label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Afrobeats night this Saturday at Muri Okunola Park, Lagos. Doors 8pm, ₦5000 at the gate..."
            rows={5}
            className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary focus:shadow-brutal-primary resize-none transition-all"
          />
        </FieldWrap>

        <FieldWrap>
          <Label>Source URL</Label>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://instagram.com/p/... or event page link"
            icon={<Link2 size={16} />}
          />
        </FieldWrap>

        <FieldWrap>
          <Label>Flyer Image</Label>
          {imagePreview ? (
            <div className="relative w-full max-w-xs">
              <img src={imagePreview} alt="Flyer preview" className="w-full rounded border-2 border-border" />
              <button
                type="button"
                onClick={() => handleImageChange(null)}
                aria-label="Remove image"
                className="absolute top-2 right-2 p-1 rounded-full bg-black/60 text-white"
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full flex flex-col items-center justify-center gap-2 py-8 rounded border-2 border-dashed border-border bg-bg-card text-text-muted hover:border-primary hover:text-primary transition-colors"
            >
              <ImageIcon size={22} />
              <span className="text-xs font-bold uppercase tracking-wide">Upload flyer image</span>
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => handleImageChange(e.target.files?.[0] ?? null)}
          />
        </FieldWrap>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <Button fullWidth loading={loading} onClick={generate}>
          <Sparkles size={16} /> Generate Draft
        </Button>
        </div>

        {draft && (
          <div className="mt-5 lg:mt-0 lg:w-96 lg:shrink-0 lg:sticky lg:top-20 border-2 border-purple-300 bg-purple-50 rounded p-4 space-y-3">
            <div className="flex items-center gap-2 text-purple-700">
              <Sparkles size={14} />
              <span className="text-xs font-black uppercase tracking-widest">AI Draft</span>
            </div>
            {draft.cover_image && (
              <img
                src={draft.cover_image}
                alt="Extracted cover"
                className="w-full h-40 object-cover rounded border-2 border-border"
              />
            )}
            <div>
              <p className="font-black text-text-primary">{draft.title || "(no title extracted)"}</p>
              <p className="text-sm text-text-secondary mt-1">{draft.description || "(no description extracted)"}</p>
            </div>
            <div className="text-xs text-text-muted space-y-0.5">
              {draft.venue_name && <p>📍 {draft.venue_name}{draft.city ? `, ${draft.city}` : ""}</p>}
              {draft.start_date && <p>🗓️ {new Date(draft.start_date).toLocaleString()}</p>}
              <p>💰 {draft.is_free ? "Free" : `${draft.currency} ${draft.price_min ?? "?"}${draft.price_max ? `–${draft.price_max}` : ""}`}</p>
              {draft.category_guess && <p>🏷️ Suggested category: {draft.category_guess}</p>}
            </div>
            {draft.confidence_notes && (
              <p className="text-[11px] italic text-text-muted flex items-start gap-1">
                <FileText size={12} className="mt-0.5 shrink-0" /> {draft.confidence_notes}
              </p>
            )}
            <div className="flex gap-2 pt-1">
              <Button size="sm" fullWidth onClick={useDraft}>Use This Draft →</Button>
              <Button size="sm" variant="secondary" onClick={() => setDraft(null)}>Discard</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
