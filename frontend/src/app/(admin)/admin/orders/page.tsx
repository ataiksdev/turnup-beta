"use client";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { adminApi, AdminOrderOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(dateStr).toLocaleDateString("en-NG", { day: "2-digit", month: "short" });
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    confirmed: "border-green-400 text-green-700 bg-green-50",
    pending: "border-yellow-400 text-yellow-700 bg-yellow-50",
    cancelled: "border-red-400 text-red-700 bg-red-50",
    refunded: "border-blue-400 text-blue-700 bg-blue-50",
  };
  return (
    <span className={cn("text-xs font-bold px-2 py-0.5 rounded border-2", colors[status] ?? "border-border text-text-muted bg-bg-elevated")}>
      {status}
    </span>
  );
}

function OrderRow({ order, onRefunded }: { order: AdminOrderOut; onRefunded: (orderId: string) => void }) {
  const { token } = useAuthStore();
  const [confirming, setConfirming] = useState(false);

  const refundMutation = useMutation({
    mutationFn: () => adminApi.refundOrder(token!, order.id),
    onSuccess: () => onRefunded(order.id),
  });

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <p className="font-black text-text-primary text-sm truncate flex-1">{order.event_title}</p>
        <StatusBadge status={order.status} />
      </div>
      <div className="text-xs text-text-muted space-y-0.5">
        <p>@{order.buyer_username}{order.buyer_email ? ` · ${order.buyer_email}` : ""}</p>
        <p>{order.tier_name} · {order.quantity} × ₦{order.unit_price.toLocaleString("en-NG")} = <span className="font-black text-text-primary">₦{order.total_price.toLocaleString("en-NG")}</span></p>
        {!!order.platform_fee_amount && (
          <p>Turnup fee: ₦{order.platform_fee_amount.toLocaleString("en-NG")}</p>
        )}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted">{timeAgo(order.created_at)}</p>
        {order.status === "confirmed" && (
          confirming ? (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="danger" loading={refundMutation.isPending} onClick={() => refundMutation.mutate()}>
                Confirm
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="text-[10px] font-black text-red-600 uppercase tracking-widest hover:underline"
            >
              Refund
            </button>
          )
        )}
      </div>
    </div>
  );
}

const PAGE_SIZE = 50;

export default function AdminOrdersPage() {
  const { token } = useAuthStore();
  const [skip, setSkip] = useState(0);
  const [allOrders, setAllOrders] = useState<AdminOrderOut[]>([]);

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["admin-orders", skip],
    queryFn: async () => {
      const result = await adminApi.orders(token!, { skip });
      if (skip === 0) {
        setAllOrders(result);
      } else {
        setAllOrders((prev) => [...prev, ...result]);
      }
      return result;
    },
    enabled: !!token,
  });

  function handleRefunded(orderId: string) {
    setAllOrders((prev) => prev.map((o) => o.id === orderId ? { ...o, status: "refunded" } : o));
  }

  const confirmedRevenue = allOrders
    .filter((o) => o.status === "confirmed")
    .reduce((sum, o) => sum + o.total_price, 0);

  const hasMore = data && data.length === PAGE_SIZE;

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Platform Orders" back />

      <div className="px-4 py-4 space-y-4">
        {allOrders.length > 0 && (
          <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4">
            <p className="text-sm font-black text-text-primary">
              ₦{confirmedRevenue.toLocaleString("en-NG")} total confirmed revenue · {allOrders.length} orders
            </p>
          </div>
        )}

        {error && (
          <p className="text-red-500 text-sm">{(error as Error).message}</p>
        )}

        {isLoading && skip === 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-24" />
            ))}
          </div>
        ) : allOrders.length > 0 ? (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
              {allOrders.map((order) => (
                <OrderRow key={order.id} order={order} onRefunded={handleRefunded} />
              ))}
            </div>
            {hasMore && (
              <Button
                fullWidth
                variant="secondary"
                loading={isFetching}
                onClick={() => setSkip((s) => s + PAGE_SIZE)}
              >
                Load more
              </Button>
            )}
          </>
        ) : (
          <p className="text-center text-text-muted text-sm py-12">No orders found</p>
        )}
      </div>
    </div>
  );
}
