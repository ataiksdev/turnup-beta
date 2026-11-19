"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { portalApi, type PortalVenue } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

export function useVenue(id: string) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal", id], queryFn: () => portalApi.get(token!, id), enabled: !!token && !!id });
  return {
    ...q, token: token!,
    setVenue: (v: PortalVenue) => qc.setQueryData(["portal", id], v),
    refresh: () => qc.invalidateQueries({ queryKey: ["portal", id] }),
  };
}

export const canManage = (v?: PortalVenue) => v?.my_role === "owner" || v?.my_role === "manager";
export const isOwner = (v?: PortalVenue) => v?.my_role === "owner";

export function Card({ title, children, actions }: { title?: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <section className="p-4 rounded border-2 border-border bg-bg-card space-y-3">
      {(title || actions) && (
        <div className="flex items-center gap-2">
          {title && <h2 className="text-xs font-black uppercase tracking-widest text-text">{title}</h2>}
          <div className="ml-auto">{actions}</div>
        </div>
      )}
      {children}
    </section>
  );
}

export const fieldCls = "w-full h-10 rounded border-2 border-border bg-bg px-3 text-sm text-text";
export const labelCls = "block text-[11px] font-bold uppercase text-text-secondary space-y-1";

export function toLocalInput(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
