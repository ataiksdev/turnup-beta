"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { TopBar } from "@/components/layout/TopBar";
import { cn } from "@/lib/utils";
import { AI_DRAFT_SESSION_KEY } from "@/lib/aiDraft";
import {
  AlignLeft, MapPin, Calendar, DollarSign, Tag, Users, Monitor, Video, Blend,
} from "lucide-react";

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-black text-text-muted uppercase tracking-widest mb-1.5">{children}</p>;
}

function FieldWrap({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("space-y-1", className)}>{children}</div>;
}

function Textarea({ value, onChange, placeholder, rows = 4 }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary focus:shadow-brutal-primary resize-none transition-all"
    />
  );
}

type EventType = "physical" | "virtual" | "hybrid";

interface FormState {
  title: string; description: string; cover_image: string;
  event_type: EventType; venue_name: string; address: string; city: string;
  country: string; meeting_url: string;
  start_date: string; end_date: string;
  is_free: boolean; price_min: string; price_max: string; currency: string;
  capacity: string; category_id: string; tags: string;
  created_via: "manual" | "ai_agent";
}

const EMPTY_FORM: FormState = {
  title: "", description: "", cover_image: "",
  event_type: "physical", venue_name: "", address: "", city: "", country: "Nigeria", meeting_url: "",
  start_date: "", end_date: "",
  is_free: true, price_min: "", price_max: "", currency: "NGN",
  capacity: "", category_id: "", tags: "",
  created_via: "manual",
};

export default function AdminCreateEventPage() {
  const router = useRouter();
  const { token, user } = useAuthStore();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isAdmin = user?.role === "admin";

  // Pick up a draft handed off from the AI-drafting screen, if present.
  useEffect(() => {
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(AI_DRAFT_SESSION_KEY) : null;
    if (raw) {
      try {
        const draft = JSON.parse(raw);
        setForm((f) => ({ ...f, ...draft, created_via: "ai_agent" }));
      } catch { /* ignore malformed draft */ }
      sessionStorage.removeItem(AI_DRAFT_SESSION_KEY);
    }
  }, []);

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => eventsApi.categories(),
  });

  function set<K extends keyof FormState>(key: K) {
    return (value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  }

  function validate(): string | null {
    if (form.title.trim().length < 5) return "Title must be at least 5 characters.";
    if (form.description.trim().length < 20) return "Description must be at least 20 characters.";
    if (form.event_type !== "virtual" && form.venue_name.trim().length < 2) return "Venue name is required.";
    if (form.event_type !== "virtual" && form.address.trim().length < 5) return "Address is required.";
    if (form.event_type !== "virtual" && form.city.trim().length < 2) return "City is required.";
    if (!form.start_date || !form.end_date) return "Start and end date/time are required.";
    if (new Date(form.end_date) <= new Date(form.start_date)) return "End date must be after the start date.";
    return null;
  }

  async function submit(status: "draft" | "published") {
    const err = validate();
    if (err) { setError(err); return; }
    if (!token) return;

    setSubmitting(true);
    setError("");
    try {
      const isVirtual = form.event_type === "virtual";
      const payload = {
        title: form.title.trim(),
        description: form.description.trim(),
        cover_image: form.cover_image.trim() || undefined,
        event_type: form.event_type,
        meeting_url: form.meeting_url.trim() || undefined,
        venue_name: isVirtual ? (form.venue_name.trim() || "Online") : form.venue_name.trim(),
        address: isVirtual ? (form.address.trim() || "Online") : form.address.trim(),
        city: isVirtual ? (form.city.trim() || "Online") : form.city.trim(),
        country: form.country.trim() || "Nigeria",
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
        is_free: form.is_free,
        price_min: !form.is_free && form.price_min ? Number(form.price_min) : undefined,
        price_max: !form.is_free && form.price_max ? Number(form.price_max) : undefined,
        currency: form.currency,
        capacity: form.capacity ? Number(form.capacity) : undefined,
        category_id: form.category_id || undefined,
        tags: form.tags.trim() || undefined,
        status,
        created_via: form.created_via,
      };
      const event = await eventsApi.create(token, payload);
      router.replace(`/admin/events?created=${event.id}`);
    } catch (e: any) {
      setError(e.message ?? "Failed to create event");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col pb-24">
      <TopBar title="Create Event" back />

      <div className="px-4 py-4 space-y-5 lg:max-w-2xl">
        {!isAdmin && (
          <p className="text-xs font-bold text-yellow-700 bg-yellow-50 border-2 border-yellow-300 rounded px-3 py-2">
            As a moderator, this event will be submitted for admin approval before it goes live.
          </p>
        )}
        {form.created_via === "ai_agent" && (
          <p className="text-xs font-bold text-purple-700 bg-purple-50 border-2 border-purple-300 rounded px-3 py-2">
            Pre-filled from an AI draft — review every field before submitting.
          </p>
        )}

        <FieldWrap>
          <Label>Event Title *</Label>
          <Input
            value={form.title}
            onChange={(e) => set("title")(e.target.value)}
            placeholder="e.g. Neon Nights: Summer Edition"
            icon={<AlignLeft size={16} />}
            maxLength={200}
          />
        </FieldWrap>

        <FieldWrap>
          <Label>Description *</Label>
          <Textarea
            value={form.description}
            onChange={set("description")}
            placeholder="What's this event about?"
          />
        </FieldWrap>

        <FieldWrap>
          <Label>Category</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {categories?.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => set("category_id")(form.category_id === cat.id ? "" : cat.id)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2.5 rounded border-2 text-sm font-bold transition-all duration-100",
                  form.category_id === cat.id
                    ? "border-primary bg-primary/10 text-primary shadow-brutal-sm"
                    : "border-border bg-bg-card text-text",
                )}
              >
                <span>{cat.icon}</span>
                <span className="uppercase tracking-wide text-[11px]">{cat.name}</span>
              </button>
            ))}
          </div>
        </FieldWrap>

        <FieldWrap>
          <Label>Format</Label>
          <div className="grid grid-cols-3 gap-2">
            {([
              { value: "physical", icon: MapPin, label: "In-person" },
              { value: "virtual", icon: Video, label: "Virtual" },
              { value: "hybrid", icon: Blend, label: "Hybrid" },
            ] as const).map(({ value, icon: Icon, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => set("event_type")(value)}
                className={cn(
                  "flex flex-col items-center gap-1 px-3 py-2.5 rounded border-2 text-xs font-bold transition-all duration-100",
                  form.event_type === value
                    ? "border-primary bg-primary/10 text-primary shadow-brutal-sm"
                    : "border-border bg-bg-card text-text",
                )}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </div>
        </FieldWrap>

        {form.event_type !== "virtual" && (
          <>
            <FieldWrap>
              <Label>Venue Name *</Label>
              <Input value={form.venue_name} onChange={(e) => set("venue_name")(e.target.value)} icon={<MapPin size={16} />} />
            </FieldWrap>
            <FieldWrap>
              <Label>Address *</Label>
              <Input value={form.address} onChange={(e) => set("address")(e.target.value)} />
            </FieldWrap>
            <div className="grid grid-cols-2 gap-3">
              <FieldWrap>
                <Label>City *</Label>
                <Input value={form.city} onChange={(e) => set("city")(e.target.value)} />
              </FieldWrap>
              <FieldWrap>
                <Label>Country</Label>
                <Input value={form.country} onChange={(e) => set("country")(e.target.value)} />
              </FieldWrap>
            </div>
          </>
        )}

        {form.event_type !== "physical" && (
          <FieldWrap>
            <Label>Meeting URL</Label>
            <Input value={form.meeting_url} onChange={(e) => set("meeting_url")(e.target.value)} icon={<Monitor size={16} />} placeholder="https://..." />
          </FieldWrap>
        )}

        <div className="grid grid-cols-2 gap-3">
          <FieldWrap>
            <Label>Starts *</Label>
            <Input type="datetime-local" value={form.start_date} onChange={(e) => set("start_date")(e.target.value)} icon={<Calendar size={16} />} />
          </FieldWrap>
          <FieldWrap>
            <Label>Ends *</Label>
            <Input type="datetime-local" value={form.end_date} onChange={(e) => set("end_date")(e.target.value)} icon={<Calendar size={16} />} />
          </FieldWrap>
        </div>

        <FieldWrap>
          <Label>Pricing</Label>
          <div className="flex gap-2 mb-2">
            <button
              type="button"
              onClick={() => set("is_free")(true)}
              className={cn("flex-1 px-3 py-2 rounded border-2 text-sm font-bold", form.is_free ? "border-primary bg-primary/10 text-primary" : "border-border bg-bg-card text-text")}
            >
              Free
            </button>
            <button
              type="button"
              onClick={() => set("is_free")(false)}
              className={cn("flex-1 px-3 py-2 rounded border-2 text-sm font-bold", !form.is_free ? "border-primary bg-primary/10 text-primary" : "border-border bg-bg-card text-text")}
            >
              Paid
            </button>
          </div>
          {!form.is_free && (
            <div className="grid grid-cols-3 gap-2">
              <Input type="number" value={form.price_min} onChange={(e) => set("price_min")(e.target.value)} placeholder="Min" icon={<DollarSign size={16} />} />
              <Input type="number" value={form.price_max} onChange={(e) => set("price_max")(e.target.value)} placeholder="Max" />
              <Input value={form.currency} onChange={(e) => set("currency")(e.target.value)} placeholder="NGN" />
            </div>
          )}
        </FieldWrap>

        <FieldWrap>
          <Label>Capacity</Label>
          <Input type="number" value={form.capacity} onChange={(e) => set("capacity")(e.target.value)} icon={<Users size={16} />} placeholder="Leave blank for unlimited" />
        </FieldWrap>

        <FieldWrap>
          <Label>Tags</Label>
          <Input value={form.tags} onChange={(e) => set("tags")(e.target.value)} icon={<Tag size={16} />} placeholder="comma, separated, tags" />
        </FieldWrap>

        <FieldWrap>
          <Label>Cover Image URL</Label>
          <Input value={form.cover_image} onChange={(e) => set("cover_image")(e.target.value)} placeholder="https://..." />
        </FieldWrap>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <div className="flex gap-2 pt-2">
          <Button variant="secondary" fullWidth loading={submitting} onClick={() => submit("draft")}>
            Save as Draft
          </Button>
          <Button fullWidth loading={submitting} onClick={() => submit("published")}>
            {isAdmin ? "Publish" : "Submit for Approval"}
          </Button>
        </div>
      </div>
    </div>
  );
}

