"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { organizerApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import { FileText, Trash2, Plus, Calendar, Zap } from "lucide-react";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function TemplateSkeleton() {
  return (
    <div className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-1/3" />
      <div className="flex gap-2 pt-1">
        <Skeleton className="h-8 flex-1" />
        <Skeleton className="h-8 w-16" />
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const router = useRouter();
  const { token } = useAuthStore();
  const queryClient = useQueryClient();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [createError, setCreateError] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const { data: templates, isLoading } = useQuery({
    queryKey: ["organizer-templates"],
    queryFn: () => organizerApi.listTemplates(token!),
    enabled: !!token,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      organizerApi.createTemplate(token!, {
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        template_data: {},
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizer-templates"] });
      setNewName("");
      setNewDesc("");
      setCreateError("");
      setShowCreateForm(false);
    },
    onError: (err: any) => {
      setCreateError(err.message ?? "Failed to create template");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => organizerApi.deleteTemplate(token!, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizer-templates"] });
      setDeleteConfirm(null);
    },
  });

  return (
    <div className="flex flex-col min-h-screen bg-bg">
      <TopBar back title="Event Templates" />

      <div className="flex-1 px-4 py-5 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-xs text-text-muted">
            {templates?.length ?? 0} template{templates?.length !== 1 ? "s" : ""}
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowCreateForm((v) => !v)}
            className="flex items-center gap-1.5"
          >
            <Plus size={14} />
            Create Template
          </Button>
        </div>

        {showCreateForm && (
          <div className="rounded border-2 border-primary/40 bg-bg-card shadow-brutal-sm p-4 space-y-3">
            <p className="text-[10px] font-black text-text uppercase tracking-widest">New Template</p>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Template name"
              maxLength={100}
              autoFocus
            />
            <Input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              maxLength={500}
            />
            {createError && (
              <p className="text-xs text-error font-medium">{createError}</p>
            )}
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!newName.trim()}
                loading={createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowCreateForm(false);
                  setNewName("");
                  setNewDesc("");
                  setCreateError("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <TemplateSkeleton key={i} />
            ))}
          </div>
        )}

        {!isLoading && templates?.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <div className="w-14 h-14 rounded border-2 border-border bg-bg-card shadow-brutal-sm flex items-center justify-center">
              <FileText size={24} className="text-text-muted" />
            </div>
            <p className="text-sm font-black text-text uppercase tracking-widest">No templates yet</p>
            <p className="text-xs text-text-muted max-w-[220px] leading-relaxed">
              Save time by creating templates for recurring events
            </p>
          </div>
        )}

        {!isLoading && templates && templates.length > 0 && (
          <div className="space-y-3">
            {templates.map((tpl) => {
              const data = tpl.template_data as Record<string, unknown>;
              const isConfirming = deleteConfirm === tpl.id;

              return (
                <div
                  key={tpl.id}
                  className="rounded border-2 border-border bg-bg-card shadow-brutal-sm p-4 space-y-3"
                >
                  <div>
                    <p className="text-base font-black text-text">{tpl.name}</p>
                    {tpl.description && (
                      <p className="text-xs text-text-muted mt-0.5 line-clamp-2">{tpl.description}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {typeof data.event_type === "string" && (
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded border text-[10px] font-black uppercase tracking-widest",
                          data.event_type === "physical" && "border-border text-text-muted",
                          data.event_type === "virtual" && "border-primary/40 text-primary bg-primary/10",
                          data.event_type === "hybrid" && "border-primary/40 text-primary bg-primary/10",
                        )}
                      >
                        {data.event_type === "physical"
                          ? "In Person"
                          : data.event_type === "virtual"
                          ? "Virtual"
                          : "Hybrid"}
                      </span>
                    )}
                    {typeof data.is_free === "boolean" && (
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded border text-[10px] font-black uppercase tracking-widest",
                          data.is_free
                            ? "border-success/40 text-success bg-success/10"
                            : "border-border text-text-muted",
                        )}
                      >
                        {data.is_free ? "Free" : "Paid"}
                      </span>
                    )}
                    <span className="text-[10px] text-text-muted flex items-center gap-1 ml-auto">
                      <Calendar size={10} />
                      Updated {timeAgo(tpl.updated_at)}
                    </span>
                  </div>

                  {isConfirming ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-error font-bold flex-1">Are you sure?</span>
                      <Button
                        size="xs"
                        variant="danger"
                        loading={deleteMutation.isPending}
                        onClick={() => deleteMutation.mutate(tpl.id)}
                      >
                        Confirm
                      </Button>
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => setDeleteConfirm(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        fullWidth
                        onClick={() => router.push(`/organizer/create?template=${tpl.id}`)}
                      >
                        <Zap size={13} />
                        Use Template
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDeleteConfirm(tpl.id)}
                        className="text-error hover:bg-error/10 shrink-0"
                      >
                        <Trash2 size={13} />
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
