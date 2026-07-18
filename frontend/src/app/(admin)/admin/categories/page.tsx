"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, AdminCategoryOut } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

function CategoryRow({ cat }: { cat: AdminCategoryOut }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [form, setForm] = useState({
    name: cat.name, slug: cat.slug, icon: cat.icon,
    color: cat.color, description: cat.description ?? "",
  });

  const updateMutation = useMutation({
    mutationFn: () => adminApi.updateCategory(token!, cat.id, {
      name: form.name, slug: form.slug, icon: form.icon,
      color: form.color, description: form.description || undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-categories"] }); setEditing(false); },
  });

  const deleteMutation = useMutation({
    mutationFn: () => adminApi.deleteCategory(token!, cat.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-categories"] }),
  });

  if (editing) {
    return (
      <div className="border-2 border-primary bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Name"
            value={form.name}
            onChange={(e) => {
              const name = e.target.value;
              setForm((f) => ({ ...f, name, slug: name.toLowerCase().replace(/\s+/g, "-") }));
            }}
          />
          <Input
            label="Slug"
            value={form.slug}
            onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Icon (emoji)"
            value={form.icon}
            onChange={(e) => setForm((f) => ({ ...f, icon: e.target.value }))}
          />
          <div className="space-y-1">
            <label className="text-xs font-bold text-text-muted uppercase tracking-wide">Color</label>
            <input
              type="color"
              value={form.color}
              onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
              className="w-full h-10 rounded border-2 border-border cursor-pointer"
            />
          </div>
        </div>
        <Input
          label="Description"
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
        />
        <div className="flex gap-2">
          <Button size="sm" loading={updateMutation.isPending} onClick={() => updateMutation.mutate()}>
            Save
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
        {updateMutation.error && (
          <p className="text-red-500 text-sm">{(updateMutation.error as Error).message}</p>
        )}
      </div>
    );
  }

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4">
      <div className="flex items-center gap-3">
        <span className="text-2xl" aria-hidden>{cat.icon}</span>
        <div
          className="w-5 h-5 rounded border-2 border-border shrink-0"
          style={{ backgroundColor: cat.color }}
          title={cat.color}
        />
        <div className="flex-1 min-w-0">
          <p className="font-black text-text-primary">{cat.name}</p>
          <p className="text-xs text-text-muted">{cat.slug}</p>
          {cat.description && (
            <p className="text-xs text-text-secondary mt-0.5 truncate">{cat.description}</p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
            Edit
          </Button>
          {confirmDelete ? (
            <>
              <Button
                size="sm"
                loading={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate()}
                className="bg-red-600 border-red-600 text-white hover:bg-red-700"
              >
                Yes
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirmDelete(false)}>
                No
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              className="border-red-300 text-red-600 hover:bg-red-50"
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function CreateCategoryForm() {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", slug: "", icon: "", color: "#000000", description: "" });

  const mutation = useMutation({
    mutationFn: () => adminApi.createCategory(token!, {
      name: form.name, slug: form.slug, icon: form.icon,
      color: form.color, description: form.description || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-categories"] });
      setForm({ name: "", slug: "", icon: "", color: "#000000", description: "" });
    },
  });

  return (
    <div className="border-2 border-border bg-bg-surface shadow-brutal-sm rounded p-4 space-y-3">
      <h3 className="text-xs font-black text-text-primary uppercase tracking-widest">New Category</h3>
      <div className="grid grid-cols-2 gap-2">
        <Input
          label="Name"
          value={form.name}
          onChange={(e) => {
            const name = e.target.value;
            setForm((f) => ({ ...f, name, slug: name.toLowerCase().replace(/\s+/g, "-") }));
          }}
          required
        />
        <Input
          label="Slug"
          value={form.slug}
          onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Input
          label="Icon (emoji)"
          value={form.icon}
          onChange={(e) => setForm((f) => ({ ...f, icon: e.target.value }))}
          required
        />
        <div className="space-y-1">
          <label className="text-xs font-bold text-text-muted uppercase tracking-wide">Color</label>
          <input
            type="color"
            value={form.color}
            onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
            className="w-full h-10 rounded border-2 border-border cursor-pointer"
          />
        </div>
      </div>
      <Input
        label="Description (optional)"
        value={form.description}
        onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
      />
      <Button
        size="sm"
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
        disabled={!form.name || !form.slug || !form.icon}
      >
        Create Category
      </Button>
      {mutation.error && (
        <p className="text-red-500 text-sm">{(mutation.error as Error).message}</p>
      )}
    </div>
  );
}

export default function AdminCategoriesPage() {
  const { token } = useAuthStore();

  const { data: categories, isLoading, error } = useQuery({
    queryKey: ["admin-categories"],
    queryFn: () => adminApi.categories(token!),
    enabled: !!token,
  });

  return (
    <div className="flex flex-col pb-4">
      <TopBar title="Category Management" back />

      <div className="px-4 py-4 space-y-4">
        {error && (
          <p className="text-red-500 text-sm">{(error as Error).message}</p>
        )}

        <div className="space-y-3">
          <h2 className="text-xs font-black text-text-primary uppercase tracking-widest">Categories</h2>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="animate-pulse bg-bg-elevated rounded h-16" />
              ))}
            </div>
          ) : categories && categories.length > 0 ? (
            <div className="space-y-3">
              {categories.map((cat) => (
                <CategoryRow key={cat.id} cat={cat} />
              ))}
            </div>
          ) : (
            <p className="text-center text-text-muted text-sm py-8">No categories yet</p>
          )}
        </div>

        <CreateCategoryForm />
      </div>
    </div>
  );
}
