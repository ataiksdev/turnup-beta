"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import Link from "next/link";
import {
  Users, Briefcase, CalendarDays, CheckCircle,
  ShoppingBag, TrendingUp, UserPlus, CalendarPlus, Percent, Wallet,
} from "lucide-react";

function KpiCard({
  icon: Icon,
  label,
  value,
  iconClass,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  iconClass: string;
}) {
  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={18} className={iconClass} aria-hidden />
        <span className="text-xs font-bold uppercase text-text-muted">{label}</span>
      </div>
      <p className="text-2xl font-black text-text-primary">{value}</p>
    </div>
  );
}

function PlatformFeeCard() {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [percent, setPercent] = useState("");

  const { data: fee, isLoading } = useQuery({
    queryKey: ["admin-platform-fee"],
    queryFn: () => adminApi.platformFee(token!),
    enabled: !!token,
  });

  useEffect(() => {
    if (fee) setPercent(String(fee.ticket_fee_percent));
  }, [fee]);

  const updateMutation = useMutation({
    mutationFn: () => adminApi.updatePlatformFee(token!, Number(percent)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-platform-fee"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
    },
  });

  const dirty = fee && Number(percent) !== fee.ticket_fee_percent;

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Percent size={16} className="text-primary" aria-hidden />
        <span className="text-xs font-black text-text-primary uppercase tracking-widest">Ticket Platform Fee</span>
      </div>
      <p className="text-xs text-text-muted">
        The percentage of each confirmed paid order Turnup retains, deducted from the organizer's payout. Buyers never pay extra for it. Free tickets are never charged a fee.
      </p>
      {isLoading ? (
        <div className="animate-pulse bg-bg-elevated rounded h-11 w-32" />
      ) : (
        <div className="flex items-end gap-2 max-w-xs">
          <Input
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={percent}
            onChange={(e) => setPercent(e.target.value)}
            icon={<Percent size={14} />}
          />
          <Button size="sm" loading={updateMutation.isPending} disabled={!dirty} onClick={() => updateMutation.mutate()}>
            Save
          </Button>
        </div>
      )}
      {updateMutation.isError && (
        <p className="text-xs text-red-500">{(updateMutation.error as Error).message}</p>
      )}
      {updateMutation.isSuccess && !dirty && (
        <p className="text-xs text-green-600">Saved — applies to orders confirmed from now on.</p>
      )}
    </div>
  );
}

export default function AdminDashboardPage() {
  const { token } = useAuthStore();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => adminApi.stats(token!),
    enabled: !!token,
  });

  const today = new Date().toLocaleDateString("en-NG", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar />

      <div className="px-4 py-4 space-y-1">
        <span className="text-xs font-black text-primary uppercase tracking-widest">Super Admin</span>
        <h1 className="text-2xl font-black text-text-primary">Platform Overview</h1>
        <p className="text-xs font-bold text-text-muted uppercase tracking-widest">{today}</p>
      </div>

      {error && (
        <p className="mx-4 text-red-500 text-sm">{(error as Error).message}</p>
      )}

      <div className="px-4 mb-6">
        {isLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {Array.from({ length: 9 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-bg-elevated rounded h-24" />
            ))}
          </div>
        ) : stats ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            <KpiCard icon={Users}       label="Total Users"       value={stats.total_users.toLocaleString("en-NG")}       iconClass="text-blue-500" />
            <KpiCard icon={Briefcase}   label="Total Organizers"  value={stats.total_organizers.toLocaleString("en-NG")}  iconClass="text-purple-500" />
            <KpiCard icon={CalendarDays} label="Total Events"     value={stats.total_events.toLocaleString("en-NG")}      iconClass="text-green-500" />
            <KpiCard icon={CheckCircle} label="Published Events"  value={stats.published_events.toLocaleString("en-NG")}  iconClass="text-emerald-500" />
            <KpiCard icon={ShoppingBag} label="Total Orders"      value={stats.total_orders.toLocaleString("en-NG")}      iconClass="text-orange-500" />
            <KpiCard icon={TrendingUp}  label="Ticket Sales"      value={`₦${stats.confirmed_revenue.toLocaleString("en-NG")}`} iconClass="text-yellow-500" />
            <KpiCard icon={Wallet}      label="Turnup Fee Revenue" value={`₦${stats.platform_fee_revenue.toLocaleString("en-NG")}`} iconClass="text-amber-500" />
            <KpiCard icon={Users}       label="Total Attendees"   value={stats.total_attendees.toLocaleString("en-NG")}   iconClass="text-pink-500" />
            <KpiCard icon={UserPlus}    label="New Users (7d)"    value={stats.new_users_this_week.toLocaleString("en-NG")} iconClass="text-indigo-500" />
            <KpiCard icon={CalendarPlus} label="New Events (7d)"  value={stats.new_events_this_week.toLocaleString("en-NG")} iconClass="text-teal-500" />
          </div>
        ) : null}
      </div>

      <div className="px-4 mb-6 lg:max-w-md">
        <PlatformFeeCard />
      </div>

      <div className="px-4 space-y-3">
        <h2 className="text-xs font-black text-text-primary uppercase tracking-widest">Quick Actions</h2>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { href: "/admin/users",         label: "Manage Users"       },
            { href: "/admin/events",        label: "Moderate Events"    },
            { href: "/admin/events/new",    label: "Create Event"       },
            { href: "/admin/events/ai-new", label: "AI Draft Event"     },
            { href: "/admin/scout/sources", label: "Manage AI Scout"    },
            { href: "/admin/categories",    label: "Edit Categories"    },
            { href: "/admin/orders",        label: "View All Orders"    },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center justify-center p-3 rounded border-2 border-border bg-bg-surface shadow-brutal-sm hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal transition-all duration-100 active:translate-x-0.5 active:translate-y-0.5 active:shadow-none text-sm font-black text-text-primary uppercase tracking-wide text-center"
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
