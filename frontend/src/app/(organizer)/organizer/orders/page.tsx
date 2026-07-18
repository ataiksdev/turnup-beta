"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { organizerApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn, timeAgo } from "@/lib/utils";
import { ShoppingBag } from "lucide-react";

function formatNGN(amount: number) {
  return amount.toLocaleString("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  });
}

function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "confirmed"
      ? "border-success/40 bg-success/10 text-success"
      : s === "pending"
      ? "border-yellow-500/40 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400"
      : "border-border bg-bg-elevated text-text-muted";
  return (
    <span
      className={cn(
        "px-2 py-1 rounded border text-[10px] font-black uppercase tracking-widest",
        cls,
      )}
    >
      {status}
    </span>
  );
}

function OrderRowSkeleton() {
  return (
    <div className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 flex-1">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-48" />
        </div>
        <Skeleton className="h-5 w-16 rounded" />
      </div>
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-4 w-20" />
      </div>
    </div>
  );
}

export default function OrganizerOrdersPage() {
  const { token } = useAuthStore();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const { data: events } = useQuery({
    queryKey: ["organizer", "my-events"],
    queryFn: () => organizerApi.myEvents(token!),
    enabled: !!token,
  });

  const { data: orders, isLoading } = useQuery({
    queryKey: ["organizer", "orders", selectedEventId],
    queryFn: () => organizerApi.orders(token!, selectedEventId ?? undefined),
    enabled: !!token,
  });

  const totalOrders = orders?.length ?? 0;
  const totalRevenue =
    orders
      ?.filter((o) => o.status.toLowerCase() === "confirmed")
      .reduce((sum, o) => sum + o.total_price, 0) ?? 0;

  return (
    <div className="flex flex-col min-h-screen bg-bg pb-8">
      <TopBar title="Sales & Orders" back />

      {/* Summary bar */}
      <div className="mx-4 mt-4 flex gap-3">
        <div className="flex-1 rounded border-2 border-border bg-bg-card shadow-brutal-sm p-3 space-y-0.5">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Orders</p>
          {isLoading ? (
            <Skeleton className="h-6 w-12" />
          ) : (
            <p className="text-xl font-black text-text">{totalOrders}</p>
          )}
        </div>
        <div className="flex-1 rounded border-2 border-border bg-bg-card shadow-brutal-sm p-3 space-y-0.5">
          <p className="text-xs font-black text-text-muted uppercase tracking-widest">Revenue</p>
          {isLoading ? (
            <Skeleton className="h-6 w-24" />
          ) : (
            <p className="text-xl font-black text-text">{formatNGN(totalRevenue)}</p>
          )}
        </div>
      </div>

      {/* Event filter chips */}
      {events && events.length > 0 && (
        <div className="mt-4 flex gap-2 px-4 overflow-x-auto pb-1 no-scrollbar">
          <button
            onClick={() => setSelectedEventId(null)}
            className={cn(
              "shrink-0 px-3 py-1.5 rounded border-2 text-[10px] font-black uppercase tracking-widest transition-all shadow-brutal-sm hover:shadow-brutal",
              selectedEventId === null
                ? "border-primary bg-primary text-white"
                : "border-border bg-bg-card text-text-muted hover:border-primary hover:text-primary",
            )}
          >
            All events
          </button>
          {events.map((event) => (
            <button
              key={event.id}
              onClick={() => setSelectedEventId(event.id)}
              className={cn(
                "shrink-0 px-3 py-1.5 rounded border-2 text-[10px] font-black uppercase tracking-widest transition-all shadow-brutal-sm hover:shadow-brutal",
                selectedEventId === event.id
                  ? "border-primary bg-primary text-white"
                  : "border-border bg-bg-card text-text-muted hover:border-primary hover:text-primary",
              )}
            >
              {event.title}
            </button>
          ))}
        </div>
      )}

      {/* Orders list */}
      <div className="px-4 mt-4 space-y-3">
        <h2 className="text-xs font-black text-text uppercase tracking-widest">Orders</h2>

        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <OrderRowSkeleton key={i} />)
        ) : orders && orders.length > 0 ? (
          orders.map((order) => (
            <div
              key={order.id}
              className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-black text-text truncate">
                    @{order.buyer_username}
                  </p>
                  <p className="text-xs text-text-muted truncate">{order.buyer_email}</p>
                </div>
                <StatusBadge status={order.status} />
              </div>

              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-black text-text-muted uppercase tracking-widest border border-border rounded px-2 py-0.5">
                    {order.tier_name}
                  </span>
                  <span className="text-xs text-text-secondary">
                    {order.quantity} × {formatNGN(order.unit_price)}
                  </span>
                </div>
                <p className="text-sm font-black text-text shrink-0">
                  {formatNGN(order.total_price)}
                </p>
              </div>

              <p className="text-[10px] text-text-muted uppercase tracking-widest">
                {timeAgo(order.created_at)}
              </p>
            </div>
          ))
        ) : (
          <div className="flex flex-col items-center justify-center py-16 gap-4 border-2 border-dashed border-border rounded">
            <ShoppingBag size={36} className="text-border-strong" aria-hidden />
            <div className="text-center space-y-1">
              <p className="text-sm font-black text-text-secondary uppercase tracking-wide">
                No sales yet
              </p>
              <p className="text-xs text-text-muted">
                Orders will appear here once tickets are purchased
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
