"use client";
import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { uploadImage } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";

/** "Upload image" button that sends the chosen file to /api/uploads and hands back its URL.
 *  Sits next to the existing image-URL fields, so pasting a link still works too. */
export function ImageUploadButton({ onUploaded, label = "Upload image" }: {
  onUploaded: (url: string) => void;
  label?: string;
}) {
  const { token } = useAuthStore();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again after an error
    if (!file || !token) return;
    if (file.size > 8 * 1024 * 1024) return setError("Images can be up to 8 MB.");
    setBusy(true);
    setError("");
    try {
      onUploaded(await uploadImage(token, file));
    } catch (err: any) {
      setError(err.message ?? "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif"
        className="hidden" onChange={onPick} aria-hidden tabIndex={-1} />
      <Button type="button" variant="secondary" size="sm" loading={busy} disabled={!token}
        onClick={() => input.current?.click()}>
        <Upload size={14} /> {label}
      </Button>
      {error && <p role="alert" className="text-xs text-error">{error}</p>}
    </div>
  );
}
