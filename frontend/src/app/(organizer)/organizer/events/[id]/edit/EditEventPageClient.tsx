"use client";
import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { eventsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { TopBar } from "@/components/layout/TopBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import {
  AlignLeft, Calendar, CheckCircle2, DollarSign, FileEdit, Image, MapPin, Plus, Tag,
  Ticket, Trash2, ToggleLeft, ToggleRight, Users, Globe,
  ChevronRight, ChevronLeft, Monitor, Video, Blend,
} from "lucide-react";

type EventType = "physical" | "virtual" | "hybrid";

interface TierDraft {
  id: string;
  name: string;
  description: string;
  price: string;
  quantity: string;
  max_per_order: string;
}

interface FormState {
  title: string;
  category_id: string;
  description: string;
  cover_image: string;
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
  is_free: boolean;
  tags: string;
  status: string;
  newTiers: TierDraft[];
}

const TIMEZONES = [
  "Africa/Lagos","Africa/Nairobi",
  "America/New_York","America/Chicago","America/Denver","America/Los_Angeles",
  "America/Toronto","Europe/London","Europe/Paris","Europe/Berlin",
  "Asia/Dubai","Asia/Kolkata","Asia/Tokyo","Australia/Sydney",
];

const STEPS = ["Basics", "Time & Place", "Tickets", "Review"];

const EVENT_TYPES: { type: EventType; icon: React.ElementType; label: string; description: string }[] = [
  { type: "physical", icon: MapPin,  label: "In Person", description: "At a physical venue" },
  { type: "virtual",  icon: Monitor, label: "Virtual",   description: "Online — Zoom, Meet, etc." },
  { type: "hybrid",   icon: Blend,   label: "Hybrid",    description: "Both in-person and online" },
];

function toLocal(iso: string) {
  try { return new Date(iso).toISOString().slice(0, 16); } catch { return ""; }
}
function uid() { return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2); }
function newTier(): TierDraft {
  return { id: uid(), name: "", description: "", price: "", quantity: "", max_per_order: "10" };
}

// ── Shared UI ─────────────────────────────────────────────────────────────────

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center px-4 py-3 border-b-2 border-border">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center flex-1">
          <div className="flex flex-col items-center gap-0.5">
            <div className={cn(
              "w-6 h-6 rounded border-2 flex items-center justify-center text-[10px] font-black",
              i < current  && "bg-primary border-primary text-white",
              i === current && "bg-bg-card border-primary text-primary",
              i > current  && "bg-bg-card border-border text-text-muted",
            )}>
              {i < current ? "✓" : i + 1}
            </div>
            <span className={cn("text-[9px] font-bold uppercase tracking-widest whitespace-nowrap",
              i === current ? "text-primary" : "text-text-muted")}>
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

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-black text-text-muted uppercase tracking-widest mb-1.5">{children}</p>;
}
function FieldWrap({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("space-y-1", className)}>{children}</div>;
}
function Textarea({ value, onChange, placeholder, rows = 4, maxLength }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; maxLength?: number;
}) {
  return (
    <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      rows={rows} maxLength={maxLength}
      className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary resize-none transition-all" />
  );
}
function Toggle({ value, onChange, label, description }: {
  value: boolean; onChange: (v: boolean) => void; label: string; description?: string;
}) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      className={cn("w-full flex items-center justify-between p-4 rounded border-2 transition-all",
        value ? "border-primary bg-primary/10" : "border-border bg-bg-card")}>
      <div className="text-left">
        <p className="text-sm font-black text-text">{label}</p>
        {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
      </div>
      {value ? <ToggleRight size={24} className="text-primary shrink-0" />
              : <ToggleLeft  size={24} className="text-text-muted shrink-0" />}
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function EditEventPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { token } = useAuthStore();

  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [ready, setReady] = useState(false);

  const [form, setForm] = useState<FormState>({
    title: "", category_id: "", description: "", cover_image: "",
    event_type: "physical", venue_name: "", address: "", city: "", country: "US", meeting_url: "",
    start_date: "", end_date: "", timezone: "Africa/Lagos",
    capacity: "", waitlist_enabled: false,
    is_free: true, tags: "", status: "published",
    newTiers: [],
  });

  const { data: event, isLoading } = useQuery({
    queryKey: ["event", id],
    queryFn: () => eventsApi.get(id, token ?? undefined),
    enabled: !!id,
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => eventsApi.categories(),
  });

  const { data: existingTiers } = useQuery({
    queryKey: ["tiers", id],
    queryFn: () => eventsApi.tiers(id),
    enabled: !!id,
  });

  // Pre-populate form once event loads
  useEffect(() => {
    if (!event || ready) return;
    setForm({
      title: event.title ?? "",
      category_id: event.category?.id ?? "",
      description: event.description ?? "",
      cover_image: event.cover_image ?? "",
      event_type: (event.event_type as EventType) ?? "physical",
      venue_name: event.venue_name ?? "",
      address: event.address ?? "",
      city: event.city ?? "",
      country: event.country ?? "US",
      meeting_url: event.meeting_url ?? "",
      start_date: toLocal(event.start_date),
      end_date: toLocal(event.end_date),
      timezone: event.timezone ?? "Africa/Lagos",
      capacity: event.capacity ? String(event.capacity) : "",
      waitlist_enabled: event.waitlist_enabled ?? false,
      is_free: event.is_free ?? true,
      tags: event.tags ?? "",
      status: event.status ?? "published",
      newTiers: [],
    });
    setReady(true);
  }, [event, ready]);

  const set = (field: keyof FormState) => (value: string | boolean) =>
    setForm((f) => ({ ...f, [field]: value }));

  function updateTier(tid: string, field: keyof TierDraft, value: string) {
    setForm((f) => ({ ...f, newTiers: f.newTiers.map((t) => t.id === tid ? { ...t, [field]: value } : t) }));
  }
  function addTier() { setForm((f) => ({ ...f, newTiers: [...f.newTiers, newTier()] })); }
  function removeTier(tid: string) { setForm((f) => ({ ...f, newTiers: f.newTiers.filter((t) => t.id !== tid) })); }

  function validateStep(): string {
    if (step === 0) {
      if (form.title.trim().length < 5) return "Title must be at least 5 characters";
      if (form.description.trim().length < 20) return "Description must be at least 20 characters";
    }
    if (step === 1) {
      if (!form.venue_name.trim()) return "Venue name is required";
      if (form.event_type !== "virtual" && !form.address.trim()) return "Address is required";
      if (form.event_type !== "virtual" && !form.city.trim()) return "City is required";
      if (form.event_type !== "physical" && !form.meeting_url.trim()) return "Meeting URL is required";
      if (!form.start_date || !form.end_date) return "Start and end dates are required";
      if (new Date(form.end_date) <= new Date(form.start_date)) return "End date must be after start date";
    }
    if (step === 2 && !form.is_free) {
      for (const t of form.newTiers) {
        if (!t.name.trim()) return "Each new tier needs a name";
        if (!t.price || isNaN(Number(t.price)) || Number(t.price) < 0) return "Each new tier needs a valid price";
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
  function back() { setError(""); setStep((s) => s - 1); }

  async function save(publishStatus?: "draft" | "published") {
    const err = validateStep();
    if (err) { setError(err); return; }
    if (!token) return;

    setSubmitting(true);
    setError("");
    try {
      const isVirtual = form.event_type === "virtual";
      await eventsApi.update(token, id, {
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
        capacity: form.capacity ? Number(form.capacity) : undefined,
        waitlist_enabled: form.waitlist_enabled,
        tags: form.tags.trim() || undefined,
        ...(publishStatus ? { status: publishStatus } : {}),
      } as any);

      // Create any new tiers added during edit
      if (!form.is_free && form.newTiers.length > 0) {
        await Promise.all(form.newTiers.map((t) =>
          eventsApi.createTier(token, id, {
            name: t.name.trim(),
            description: t.description.trim() || undefined,
            price: Number(t.price),
            quantity: t.quantity ? Number(t.quantity) : null,
            max_per_order: t.max_per_order ? Number(t.max_per_order) : 10,
          })
        ));
      }

      router.replace("/organizer/events");
    } catch (err: any) {
      setError(err.message ?? "Failed to save event");
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading || !ready) {
    return (
      <div className="flex flex-col min-h-screen bg-bg">
        <TopBar back title="Edit Event" />
        <div className="px-4 py-5 space-y-4">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
        </div>
      </div>
    );
  }

  // ── Step content ──────────────────────────────────────────────────────────

  const step0 = (
    <div className="space-y-5">
      <FieldWrap>
        <Label>Event Title *</Label>
        <Input value={form.title} onChange={(e) => set("title")(e.target.value)}
          placeholder="e.g. Neon Nights: Summer Edition" icon={<AlignLeft size={16} />} maxLength={200} />
      </FieldWrap>

      <FieldWrap>
        <Label>Category</Label>
        <div className="grid grid-cols-2 gap-2">
          {categories?.map((cat) => (
            <button key={cat.id} type="button"
              onClick={() => set("category_id")(form.category_id === cat.id ? "" : cat.id)}
              className={cn(
                "flex items-center gap-2 px-3 py-2.5 rounded border-2 text-sm font-bold transition-all duration-100",
                "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm active:translate-x-0.5 active:translate-y-0.5",
                form.category_id === cat.id ? "border-primary bg-primary/10 text-primary shadow-brutal-sm" : "border-border bg-bg-card text-text",
              )}>
              <span>{cat.icon}</span>
              <span className="uppercase tracking-wide text-[11px]">{cat.name}</span>
              {form.category_id === cat.id && <span className="ml-auto text-[10px]">✓</span>}
            </button>
          ))}
        </div>
      </FieldWrap>

      <FieldWrap>
        <Label>Description * <span className="normal-case text-text-disabled">({form.description.length}/2000)</span></Label>
        <Textarea value={form.description} onChange={set("description")}
          placeholder="Tell people what to expect…" rows={6} maxLength={2000} />
      </FieldWrap>

      <FieldWrap>
        <Label>Cover Image URL</Label>
        <Input value={form.cover_image} onChange={(e) => set("cover_image")(e.target.value)}
          placeholder="https://..." icon={<Image size={16} />} />
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

  const step1 = (
    <div className="space-y-5">
      <FieldWrap>
        <Label>Event Format *</Label>
        <div className="grid grid-cols-3 gap-2">
          {EVENT_TYPES.map(({ type, icon: Icon, label, description }) => (
            <button key={type} type="button" onClick={() => set("event_type")(type)}
              className={cn(
                "flex flex-col items-center gap-1.5 p-3 rounded border-2 transition-all duration-100 text-center",
                "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-sm active:translate-x-0.5 active:translate-y-0.5",
                form.event_type === type ? "border-primary bg-primary/10 shadow-brutal-sm" : "border-border bg-bg-card",
              )}>
              <Icon size={18} className={form.event_type === type ? "text-primary" : "text-text-muted"} />
              <span className={cn("text-[11px] font-black uppercase tracking-wide",
                form.event_type === type ? "text-primary" : "text-text")}>{label}</span>
              <span className="text-[9px] text-text-muted leading-tight">{description}</span>
            </button>
          ))}
        </div>
      </FieldWrap>

      <FieldWrap>
        <Label>{form.event_type === "virtual" ? "Platform / Event Name *" : "Venue Name *"}</Label>
        <Input value={form.venue_name} onChange={(e) => set("venue_name")(e.target.value)}
          placeholder={form.event_type === "virtual" ? "e.g. Zoom Webinar" : "e.g. Warehouse 23"}
          icon={<MapPin size={16} />} />
      </FieldWrap>

      {form.event_type !== "physical" && (
        <FieldWrap>
          <Label>Meeting URL *</Label>
          <Input value={form.meeting_url} onChange={(e) => set("meeting_url")(e.target.value)}
            placeholder="https://zoom.us/j/..." icon={<Video size={16} />} type="url" />
        </FieldWrap>
      )}

      {form.event_type !== "virtual" && (
        <>
          <FieldWrap>
            <Label>Address *</Label>
            <Input value={form.address} onChange={(e) => set("address")(e.target.value)}
              placeholder="123 Main St" icon={<MapPin size={16} />} />
          </FieldWrap>
          <div className="grid grid-cols-2 gap-3">
            <FieldWrap>
              <Label>City *</Label>
              <Input value={form.city} onChange={(e) => set("city")(e.target.value)} placeholder="Lagos" />
            </FieldWrap>
            <FieldWrap>
              <Label>Country</Label>
              <Input value={form.country} onChange={(e) => set("country")(e.target.value)}
                placeholder="US" maxLength={2} icon={<Globe size={16} />} />
            </FieldWrap>
          </div>
        </>
      )}

      <FieldWrap>
        <Label>Start Date & Time *</Label>
        <input type="datetime-local" value={form.start_date} onChange={(e) => set("start_date")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary transition-all" />
      </FieldWrap>

      <FieldWrap>
        <Label>End Date & Time *</Label>
        <input type="datetime-local" value={form.end_date} onChange={(e) => set("end_date")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary transition-all" />
      </FieldWrap>

      <FieldWrap>
        <Label>Timezone</Label>
        <select value={form.timezone} onChange={(e) => set("timezone")(e.target.value)}
          className="w-full bg-bg-card border-2 border-border rounded px-3 py-2.5 text-sm text-text focus:outline-none focus:border-primary transition-all appearance-none">
          {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz.replace("_", " ")}</option>)}
        </select>
      </FieldWrap>

      <FieldWrap>
        <Label>Capacity</Label>
        <Input type="number" value={form.capacity} onChange={(e) => set("capacity")(e.target.value)}
          placeholder="Leave blank for unlimited" icon={<Users size={16} />} min="1" />
      </FieldWrap>

      <Toggle value={form.waitlist_enabled} onChange={set("waitlist_enabled")}
        label="Enable waitlist" description="Let people join when capacity is full" />
    </div>
  );

  const step2 = (
    <div className="space-y-5">
      <Toggle value={form.is_free} onChange={set("is_free")}
        label="This event is free" description="No payment required to attend" />

      {/* Existing tiers — read only */}
      {existingTiers && existingTiers.length > 0 && (
        <div className="space-y-2">
          <Label>Existing Tiers</Label>
          {existingTiers.map((t) => (
            <div key={t.id} className={cn(
              "flex items-center justify-between p-3 rounded border-2 border-border bg-bg-card",
              !t.is_active && "opacity-50",
            )}>
              <div>
                <p className="text-sm font-black text-text">{t.name}</p>
                <p className="text-xs text-text-muted">
                  {t.quantity !== null ? `${t.quantity - t.quantity_sold} left` : "Unlimited"}
                  {!t.is_active && " · Inactive"}
                </p>
              </div>
              <span className="text-sm font-black text-primary">${t.price.toFixed(2)}</span>
            </div>
          ))}
          <p className="text-[10px] text-text-muted">Existing tiers are view-only. Add new tiers below.</p>
        </div>
      )}

      {/* New tiers */}
      {!form.is_free && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Add New Tiers</Label>
            <button type="button" onClick={addTier}
              className="flex items-center gap-1 text-[10px] font-black text-primary uppercase tracking-widest hover:text-primary/80">
              <Plus size={12} /> Add tier
            </button>
          </div>

          {form.newTiers.map((tier, idx) => (
            <div key={tier.id} className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-text uppercase tracking-widest">New Tier {idx + 1}</span>
                <button type="button" onClick={() => removeTier(tier.id)}
                  className="p-1 rounded hover:bg-error/10 text-text-muted hover:text-error transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>

              <Input label="Tier Name" value={tier.name} onChange={(e) => updateTier(tier.id, "name", e.target.value)}
                placeholder="e.g. VIP, General Admission" icon={<Ticket size={14} />} required />

              <div className="grid grid-cols-2 gap-3">
                <FieldWrap>
                  <Label>Price (NGN) *</Label>
                  <Input type="number" value={tier.price} onChange={(e) => updateTier(tier.id, "price", e.target.value)}
                    placeholder="0.00" icon={<DollarSign size={14} />} min="0" step="0.01" />
                </FieldWrap>
                <FieldWrap>
                  <Label>Quantity</Label>
                  <Input type="number" value={tier.quantity} onChange={(e) => updateTier(tier.id, "quantity", e.target.value)}
                    placeholder="Unlimited" icon={<Users size={14} />} min="1" />
                </FieldWrap>
              </div>
            </div>
          ))}
        </div>
      )}

      <FieldWrap>
        <Label>Tags</Label>
        <Input value={form.tags} onChange={(e) => set("tags")(e.target.value)}
          placeholder="afrobeats, rooftop, 18+" icon={<Tag size={16} />} />
        <p className="text-[10px] text-text-muted">Comma-separated</p>
      </FieldWrap>
    </div>
  );

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
            <span className={cn("inline-block px-2 py-0.5 rounded border text-[10px] font-black uppercase tracking-widest",
              form.event_type === "physical" ? "border-border text-text-muted"
                : form.event_type === "virtual" ? "border-info/40 text-info bg-info/10"
                : "border-primary/40 text-primary bg-primary/10")}>
              {form.event_type === "physical" ? "In Person" : form.event_type === "virtual" ? "Virtual" : "Hybrid"}
            </span>
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
              {form.is_free ? "Free" : "Paid"}
            </div>
          </div>
        </div>
      </div>

      {/* Current status + publish toggle */}
      <div className={cn("flex items-center justify-between p-4 rounded border-2",
        form.status === "published" ? "border-success/40 bg-success/10" : "border-border bg-bg-card")}>
        <div>
          <p className="flex items-center gap-1.5 text-sm font-black text-text uppercase tracking-wide">
            {form.status === "published"
              ? <><CheckCircle2 size={14} className="text-success" /> Published</>
              : <><FileEdit size={14} className="text-text-muted" /> Draft</>}
          </p>
          <p className="text-xs text-text-muted mt-0.5">
            {form.status === "published" ? "Visible to everyone" : "Only you can see this"}
          </p>
        </div>
        {form.status === "draft" && (
          <Button size="sm" onClick={() => save("published")} loading={submitting}>
            Publish
          </Button>
        )}
        {form.status === "published" && (
          <button type="button" onClick={() => save("draft")}
            className="text-xs font-black text-text-muted uppercase tracking-widest hover:text-error transition-colors">
            Unpublish
          </button>
        )}
      </div>

      <Button fullWidth size="lg" loading={submitting} onClick={() => save()}>
        Save Changes
      </Button>
    </div>
  );

  const stepContent = [step0, step1, step2, step3];

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <TopBar back title="Edit Event" />
      <StepBar current={step} />

      <div className="flex-1 px-4 py-5 pb-8">
        {error && (
          <div className="mb-4 px-4 py-3 rounded border-2 border-error/30 bg-error/10 text-sm text-error font-medium">
            {error}
          </div>
        )}

        {stepContent[step]}

        {step < 3 && (
          <div className="flex gap-3 mt-8">
            {step > 0 && (
              <button type="button" onClick={back}
                className="flex items-center gap-1 px-4 py-3 rounded border-2 border-border bg-bg-card text-sm font-black text-text-muted uppercase tracking-widest hover:border-primary hover:text-text shadow-brutal-sm transition-all">
                <ChevronLeft size={14} /> Back
              </button>
            )}
            <Button fullWidth onClick={next}>
              Continue <ChevronRight size={14} className="ml-1" />
            </Button>
          </div>
        )}

        {step === 3 && (
          <button type="button" onClick={back}
            className="flex items-center gap-1 mt-4 px-4 py-2 rounded text-sm font-black text-text-muted uppercase tracking-widest hover:text-text transition-colors">
            <ChevronLeft size={14} /> Back
          </button>
        )}
      </div>
    </div>
  );
}
