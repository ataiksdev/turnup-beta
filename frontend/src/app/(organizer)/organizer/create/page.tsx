"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { TopBar } from "@/components/layout/TopBar";
import { cn } from "@/lib/utils";
import {
  AlignLeft, Calendar, DollarSign, Image, MapPin,
  Plus, Tag, Ticket, Trash2, ToggleLeft, ToggleRight,
  Users, Globe, ChevronRight, ChevronLeft, Monitor, Video, Blend,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TierDraft {
  id: string;
  name: string;
  description: string;
  price: string;
  quantity: string;
  max_per_order: string;
}

type EventType = "physical" | "virtual" | "hybrid";

interface FormState {
  // Step 1 — Basics
  title: string;
  category_id: string;
  description: string;
  // Step 2 — Location & Time
  event_type: EventType;
  venue_name: string;
  address: string;
  city: string;
  country: string;
  meeting_url: string;
  start_date: string;
  end_date: string;
  timezone: string;
  capacity: string;
  waitlist_enabled: boolean;
  // Step 3 — Tickets
  is_free: boolean;
  cover_image: string;
  tags: string;
  tiers: TierDraft[];
}

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Toronto",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Africa/Lagos",
  "Africa/Nairobi",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const STEPS = ["Basics", "Time & Place", "Tickets", "Review"];

function newTier(): TierDraft {
  return { id: crypto.randomUUID(), name: "", description: "", price: "", quantity: "", max_per_order: "10" };
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 px-4 py-3 border-b-2 border-border">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center flex-1">
          <div className="flex flex-col items-center gap-0.5">
            <div className={cn(
              "w-6 h-6 rounded border-2 flex items-center justify-center text-[10px] font-black transition-colors",
              i < current  && "bg-primary border-primary text-white",
              i === current && "bg-bg-card border-primary text-primary",
              i > current  && "bg-bg-card border-border text-text-muted",
            )}>
              {i < current ? "✓" : i + 1}
            </div>
            <span className={cn(
              "text-[9px] font-bold uppercase tracking-widest whitespace-nowrap",
              i === current ? "text-primary" : "text-text-muted",
            )}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={cn("flex-1 h-0.5 mx-1 mb-3", i < current ? "bg-primary" : "bg-border")} />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Shared label ─────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-black text-text-muted uppercase tracking-widest mb-1.5">{children}</p>;
}

function FieldWrap({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("space-y-1", className)}>{children}</div>;
}

// ── Textarea ─────────────────────────────────────────────────────────────────

function Textarea({ value, onChange, placeholder, rows = 4, maxLength }: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; rows?: number; maxLength?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      maxLength={maxLength}
      className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary focus:shadow-brutal-primary resize-none transition-all"
    />
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({ value, onChange, label, description }: {
  value: boolean; onChange: (v: boolean) => void; label: string; description?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={cn(
        "w-full flex items-center justify-between p-4 rounded border-2 transition-all duration-100",
        value ? "border-primary bg-primary/10" : "border-border bg-bg-card",
      )}
    >
      <div className="text-left">
        <p className="text-sm font-black text-text">{label}</p>
        {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
      </div>
      {value
        ? <ToggleRight size={24} className="text-primary shrink-0" />
        : <ToggleLeft size={24} className="text-text-muted shrink-0" />}
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CreateEventPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState<FormState>({
    title: "", category_id: "", description: "",
    event_type: "physical",
    venue_name: "", address: "", city: "", country: "US", meeting_url: "",
    start_date: "", end_date: "", timezone: "America/New_York",
    capacity: "", waitlist_enabled: false,
    is_free: true, cover_image: "", tags: "",
    tiers: [newTier()],
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => eventsApi.categories(),
  });

  const set = (field: keyof FormState) => (value: string | boolean) =>
    setForm((f) => ({ ...f, [field]: value }));

  // Tier helpers
  function updateTier(id: string, field: keyof TierDraft, value: string) {
    setForm((f) => ({ ...f, tiers: f.tiers.map((t) => t.id === id ? { ...t, [field]: value } : t) }));
  }
  function addTier() {
    setForm((f) => ({ ...f, tiers: [...f.tiers, newTier()] }));
  }
  function removeTier(id: string) {
    setForm((f) => ({ ...f, tiers: f.tiers.filter((t) => t.id !== id) }));
  }

  // Validation per step
  function validateStep(): string {
    if (step === 0) {
      if (!form.title.trim() || form.title.length < 5) return "Title must be at least 5 characters";
      if (!form.description.trim() || form.description.length < 20) return "Description must be at least 20 characters";
    }
    if (step === 1) {
      if (!form.venue_name.trim()) return "Venue name is required";
      if (form.event_type !== "virtual") {
        if (!form.address.trim()) return "Address is required";
        if (!form.city.trim()) return "City is required";
      }
      if (form.event_type !== "physical" && !form.meeting_url.trim()) return "Meeting URL is required for virtual/hybrid events";
      if (!form.start_date) return "Start date is required";
      if (!form.end_date) return "End date is required";
      if (new Date(form.end_date) <= new Date(form.start_date)) return "End date must be after start date";
    }
    if (step === 2 && !form.is_free) {
      for (const t of form.tiers) {
        if (!t.name.trim()) return "Each ticket tier needs a name";
        if (!t.price || isNaN(Number(t.price)) || Number(t.price) < 0) return "Each tier needs a valid price";
      }
    }
    return "";
  }

  function next() {
    const err = validateStep();
    if (err) { setError(err); return; }
    setError("");
    setStep((s) => s + 1);
  }

  function back() {
    setError("");
    setStep((s) => s - 1);
  }

  async function submit(status: "draft" | "published") {
    const err = validateStep();
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
        venue_name: form.venue_name.trim(),
        address: isVirtual ? (form.address.trim() || "Online") : form.address.trim(),
        city: isVirtual ? (form.city.trim() || "Online") : form.city.trim(),
        country: form.country.trim() || "US",
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
        timezone: form.timezone,
        is_free: form.is_free,
        price_min: (!form.is_free && form.tiers.length > 0)
          ? Math.min(...form.tiers.map((t) => Number(t.price) || 0))
          : undefined,
        price_max: (!form.is_free && form.tiers.length > 0)
          ? Math.max(...form.tiers.map((t) => Number(t.price) || 0))
          : undefined,
        capacity: form.capacity ? Number(form.capacity) : undefined,
        waitlist_enabled: form.waitlist_enabled,
        category_id: form.category_id || undefined,
        tags: form.tags.trim() || undefined,
        status,
      };

      const event = await eventsApi.create(token, payload);

      // Create ticket tiers for paid events
      if (!form.is_free && form.tiers.length > 0) {
        await Promise.all(
          form.tiers.map((t) =>
            eventsApi.createTier(token, event.id, {
              name: t.name.trim(),
              description: t.description.trim() || undefined,
              price: Number(t.price),
              quantity: t.quantity ? Number(t.quantity) : null,
              max_per_order: t.max_per_order ? Number(t.max_per_order) : 10,
            }),
          ),
        );
      }

      router.replace(`/organizer/events`);
    } catch (err: any) {
      setError(err.message ?? "Failed to create event");
    } finally {
      setSubmitting(false);
    }
  }

  // ── Step 1: Basics ──────────────────────────────────────────────────────────

  const step0 = (
    <div className="space-y-5">
      <FieldWrap>
        <Label>Event Title *</Label>
        <Input
          value={form.title}
          onChange={(e) => set("title")(e.target.value)}
          placeholder="e.g. Neon Nights: Summer Edition"
          icon={<AlignLeft size={16} />}
          maxLength={200}
          required
        />
      </FieldWrap>

      <FieldWrap>
        <Label>Category</Label>
        <div className="grid grid-cols-2 gap-2">
          {categories?.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => set("category_id")(form.category_id === cat.id ? "" : cat.id)}
              className={cn(
                "flex items-center gap-2 px-3 py-2.5 rounded border-2 text-sm font-bold transition-all duration-100",
                "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm active:translate-x-0.5 active:translate-y-0.5",
                form.category_id === cat.id
                  ? "border-primary bg-primary/10 text-primary shadow-brutal-sm"
                  : "border-border bg-bg-card text-text",
              )}
            >
              <span>{cat.icon}</span>
              <span className="uppercase tracking-wide text-[11px]">{cat.name}</span>
              {form.category_id === cat.id && <span className="ml-auto text-[10px]">✓</span>}
            </button>
          ))}
        </div>
      </FieldWrap>

      <FieldWrap>
        <Label>Description * <span className="normal-case text-text-disabled">({form.description.length}/2000)</span></Label>
        <Textarea
          value={form.description}
          onChange={set("description")}
          placeholder="Tell people what to expect — vibe, lineup, dress code, what's included..."
          rows={6}
          maxLength={2000}
        />
      </FieldWrap>

      <FieldWrap>
        <Label>Cover Image URL</Label>
        <Input
          value={form.cover_image}
          onChange={(e) => set("cover_image")(e.target.value)}
          placeholder="https://..."
          icon={<Image size={16} />}
        />
        {form.cover_image && (
          <div className="mt-2 h-32 w-full rounded border-2 border-border overflow-hidden bg-bg-elevated">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={form.cover_image} alt="Cover preview" className="w-full h-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          </div>
        )}
      </FieldWrap>
    </div>
  );

  // ── Step 2: Time & Place ────────────────────────────────────────────────────

  const EVENT_TYPES: { type: EventType; icon: React.ElementType; label: string; description: string }[] = [
    { type: "physical", icon: MapPin,   label: "In Person",  description: "At a physical venue" },
    { type: "virtual",  icon: Monitor,  label: "Virtual",    description: "Online — Zoom, Meet, etc." },
    { type: "hybrid",   icon: Blend,    label: "Hybrid",     description: "Both in-person and online" },
  ];

  const step1 = (
    <div className="space-y-5">
      {/* Event type selector */}
      <FieldWrap>
        <Label>Event Format *</Label>
        <div className="grid grid-cols-3 gap-2">
          {EVENT_TYPES.map(({ type, icon: Icon, label, description }) => (
            <button
              key={type}
              type="button"
              onClick={() => set("event_type")(type)}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded border-2 transition-all duration-100 text-center",
                "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm active:translate-x-0.5 active:translate-y-0.5",
                form.event_type === type
                  ? "border-primary bg-primary/10 shadow-brutal-sm"
                  : "border-border bg-bg-card",
              )}
            >
              <Icon size={18} className={form.event_type === type ? "text-primary" : "text-text-muted"} />
              <span className={cn(
                "text-[11px] font-black uppercase tracking-wide",
                form.event_type === type ? "text-primary" : "text-text",
              )}>
                {label}
              </span>
              <span className="text-[9px] text-text-muted leading-tight">{description}</span>
            </button>
          ))}
        </div>
      </FieldWrap>

      <FieldWrap>
        <Label>{form.event_type === "virtual" ? "Platform / Event Name *" : "Venue Name *"}</Label>
        <Input
          value={form.venue_name}
          onChange={(e) => set("venue_name")(e.target.value)}
          placeholder={form.event_type === "virtual" ? "e.g. Zoom Webinar, Google Meet" : "e.g. Warehouse 23, Rooftop Bar"}
          icon={<MapPin size={16} />}
          required
        />
      </FieldWrap>

      {/* Meeting URL — virtual + hybrid */}
      {form.event_type !== "physical" && (
        <FieldWrap>
          <Label>Meeting URL *</Label>
          <Input
            value={form.meeting_url}
            onChange={(e) => set("meeting_url")(e.target.value)}
            placeholder="https://zoom.us/j/..."
            icon={<Video size={16} />}
            type="url"
            required
          />
        </FieldWrap>
      )}

      {/* Physical address — physical + hybrid */}
      {form.event_type !== "virtual" && (
        <>
          <FieldWrap>
            <Label>Address *</Label>
            <Input
              value={form.address}
              onChange={(e) => set("address")(e.target.value)}
              placeholder="123 Main St"
              icon={<MapPin size={16} />}
              required
            />
          </FieldWrap>

          <div className="grid grid-cols-2 gap-3">
            <FieldWrap>
              <Label>City *</Label>
              <Input
                value={form.city}
                onChange={(e) => set("city")(e.target.value)}
                placeholder="Lagos"
                required
              />
            </FieldWrap>
            <FieldWrap>
              <Label>Country</Label>
              <Input
                value={form.country}
                onChange={(e) => set("country")(e.target.value)}
                placeholder="US"
                maxLength={2}
                icon={<Globe size={16} />}
              />
            </FieldWrap>
          </div>
        </>
      )}

      <FieldWrap>
        <Label>Start Date & Time *</Label>
        <input
          type="datetime-local"
          value={form.start_date}
          onChange={(e) => set("start_date")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary focus:shadow-brutal-primary transition-all"
          required
        />
      </FieldWrap>

      <FieldWrap>
        <Label>End Date & Time *</Label>
        <input
          type="datetime-local"
          value={form.end_date}
          onChange={(e) => set("end_date")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary focus:shadow-brutal-primary transition-all"
          required
        />
      </FieldWrap>

      <FieldWrap>
        <Label>Timezone</Label>
        <select
          value={form.timezone}
          onChange={(e) => set("timezone")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary transition-all appearance-none"
        >
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>{tz.replace("_", " ")}</option>
          ))}
        </select>
      </FieldWrap>

      <FieldWrap>
        <Label>Capacity</Label>
        <Input
          type="number"
          value={form.capacity}
          onChange={(e) => set("capacity")(e.target.value)}
          placeholder="Leave blank for unlimited"
          icon={<Users size={16} />}
          min="1"
        />
      </FieldWrap>

      <Toggle
        value={form.waitlist_enabled}
        onChange={set("waitlist_enabled")}
        label="Enable waitlist"
        description="Let people join a waitlist when capacity is full"
      />
    </div>
  );

  // ── Step 3: Tickets ─────────────────────────────────────────────────────────

  const step2 = (
    <div className="space-y-5">
      <Toggle
        value={form.is_free}
        onChange={set("is_free")}
        label="This event is free"
        description="No payment required to attend"
      />

      {!form.is_free && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Ticket Tiers</Label>
            <button
              type="button"
              onClick={addTier}
              className="flex items-center gap-1 text-[10px] font-black text-primary uppercase tracking-widest hover:text-primary/80"
            >
              <Plus size={12} /> Add tier
            </button>
          </div>

          {form.tiers.map((tier, idx) => (
            <div key={tier.id} className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-text uppercase tracking-widest">
                  Tier {idx + 1}
                </span>
                {form.tiers.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeTier(tier.id)}
                    className="p-1 rounded hover:bg-error/10 text-text-muted hover:text-error transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>

              <Input
                label="Tier Name"
                value={tier.name}
                onChange={(e) => updateTier(tier.id, "name", e.target.value)}
                placeholder="e.g. Early Bird, VIP, General Admission"
                icon={<Ticket size={14} />}
                required
              />

              <div className="grid grid-cols-2 gap-3">
                <FieldWrap>
                  <Label>Price (NGN) *</Label>
                  <Input
                    type="number"
                    value={tier.price}
                    onChange={(e) => updateTier(tier.id, "price", e.target.value)}
                    placeholder="0.00"
                    icon={<DollarSign size={14} />}
                    min="0"
                    step="0.01"
                    required
                  />
                </FieldWrap>
                <FieldWrap>
                  <Label>Quantity</Label>
                  <Input
                    type="number"
                    value={tier.quantity}
                    onChange={(e) => updateTier(tier.id, "quantity", e.target.value)}
                    placeholder="Unlimited"
                    icon={<Users size={14} />}
                    min="1"
                  />
                </FieldWrap>
              </div>

              <FieldWrap>
                <Label>Max per order</Label>
                <Input
                  type="number"
                  value={tier.max_per_order}
                  onChange={(e) => updateTier(tier.id, "max_per_order", e.target.value)}
                  placeholder="10"
                  min="1"
                  max="100"
                />
              </FieldWrap>

              <FieldWrap>
                <Label>Tier description (optional)</Label>
                <Input
                  value={tier.description}
                  onChange={(e) => updateTier(tier.id, "description", e.target.value)}
                  placeholder="What's included in this tier?"
                />
              </FieldWrap>
            </div>
          ))}
        </div>
      )}

      <FieldWrap>
        <Label>Tags</Label>
        <Input
          value={form.tags}
          onChange={(e) => set("tags")(e.target.value)}
          placeholder="afrobeats, rooftop, 18+"
          icon={<Tag size={16} />}
        />
        <p className="text-[10px] text-text-muted">Comma-separated</p>
      </FieldWrap>
    </div>
  );

  // ── Step 4: Review ──────────────────────────────────────────────────────────

  const step3 = (
    <div className="space-y-4">
      <div className="rounded border-2 border-border bg-bg-card shadow-brutal overflow-hidden">
        {form.cover_image && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={form.cover_image} alt="" className="w-full h-40 object-cover border-b-2 border-border" />
        )}
        <div className="p-4 space-y-3">
          <h2 className="text-lg font-black text-text">{form.title || "Untitled Event"}</h2>
          <p className="text-xs text-text-muted line-clamp-3">{form.description}</p>

          <div className="space-y-1.5 pt-1">
            <div className="flex items-center gap-2">
              <span className={cn(
                "px-2 py-0.5 rounded border text-[10px] font-black uppercase tracking-widest",
                form.event_type === "physical" ? "border-border text-text-muted"
                  : form.event_type === "virtual" ? "border-[#3B82F6]/40 text-[#3B82F6] bg-[#3B82F6]/10"
                  : "border-primary/40 text-primary bg-primary/10",
              )}>
                {form.event_type === "physical" ? "In Person"
                  : form.event_type === "virtual" ? "Virtual"
                  : "Hybrid"}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <Calendar size={12} className="text-primary" />
              {form.start_date ? new Date(form.start_date).toLocaleString() : "—"}
            </div>
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <MapPin size={12} className="text-primary" />
              {[form.venue_name, form.event_type !== "virtual" ? form.city : "Online"].filter(Boolean).join(", ") || "—"}
            </div>
            {form.event_type !== "physical" && form.meeting_url && (
              <div className="flex items-center gap-2 text-xs text-text-secondary">
                <Monitor size={12} className="text-primary" />
                <span className="truncate">{form.meeting_url}</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <DollarSign size={12} className="text-primary" />
              {form.is_free ? "Free" : form.tiers.length > 0
                ? `$${Math.min(...form.tiers.map((t) => Number(t.price) || 0))} – $${Math.max(...form.tiers.map((t) => Number(t.price) || 0))}`
                : "Paid"}
            </div>
            {form.capacity && (
              <div className="flex items-center gap-2 text-xs text-text-secondary">
                <Users size={12} className="text-primary" />
                Capacity: {form.capacity}
              </div>
            )}
          </div>
        </div>
      </div>

      {!form.is_free && form.tiers.length > 0 && (
        <div className="space-y-2">
          <Label>Ticket Tiers</Label>
          {form.tiers.map((t, i) => (
            <div key={t.id} className="flex items-center justify-between p-3 rounded border-2 border-border bg-bg-card">
              <div>
                <p className="text-sm font-black text-text">{t.name || `Tier ${i + 1}`}</p>
                {t.quantity && <p className="text-xs text-text-muted">{t.quantity} available</p>}
              </div>
              <span className="text-sm font-black text-primary">${Number(t.price || 0).toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="pt-2 space-y-3">
        <Button fullWidth size="lg" loading={submitting} onClick={() => submit("published")}>
          Publish Event
        </Button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("draft")}
          className="w-full py-3 rounded border-2 border-border bg-bg-card text-sm font-black text-text-muted uppercase tracking-widest hover:border-primary hover:text-text shadow-brutal-sm transition-all disabled:opacity-50"
        >
          Save as Draft
        </button>
      </div>
    </div>
  );

  const stepContent = [step0, step1, step2, step3];

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <TopBar back title="Create Event" />
      <StepBar current={step} />

      <div className="flex-1 px-4 py-5 pb-8">
        {error && (
          <div className="mb-4 px-4 py-3 rounded border-2 border-error/30 bg-error/10 text-sm text-error font-medium">
            {error}
          </div>
        )}

        {stepContent[step]}

        {/* Nav buttons (not shown on review step — it has its own) */}
        {step < 3 && (
          <div className="flex gap-3 mt-8">
            {step > 0 && (
              <button
                type="button"
                onClick={back}
                className="flex items-center gap-1 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-black text-text-muted uppercase tracking-widest hover:border-primary hover:text-text shadow-brutal-sm transition-all"
              >
                <ChevronLeft size={14} /> Back
              </button>
            )}
            <Button fullWidth onClick={next}>
              Continue <ChevronRight size={14} className="ml-1" />
            </Button>
          </div>
        )}

        {step === 3 && (
          <button
            type="button"
            onClick={back}
            className="flex items-center gap-1 mt-4 px-4 py-2 rounded text-sm font-black text-text-muted uppercase tracking-widest hover:text-text transition-colors"
          >
            <ChevronLeft size={14} /> Edit
          </button>
        )}
      </div>
    </div>
  );
}
