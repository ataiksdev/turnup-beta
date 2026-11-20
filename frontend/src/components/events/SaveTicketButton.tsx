"use client";
import { Download } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}

/** Saves the ticket as an image styled like a real ticket (made by the API, so it's the same
 *  everywhere). Android app: the share sheet (Save to device, Photos, WhatsApp...). Phone
 *  browsers that can share files: the share sheet. Otherwise: a normal download. */
export function SaveTicketButton({ orderId }: { orderId: string }) {
  const { token } = useAuthStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${BASE}/api/organizer/tickets/${orderId}/image.png`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(res.status, typeof err.detail === "string" ? err.detail : "Couldn't make the ticket image.");
      }
      const blob = await res.blob();
      const filename = `turnup-ticket-${orderId.slice(0, 8)}.png`;

      const { Capacitor } = await import("@capacitor/core");
      if (Capacitor.isNativePlatform()) {
        const { Filesystem, Directory } = await import("@capacitor/filesystem");
        const { Share } = await import("@capacitor/share");
        const written = await Filesystem.writeFile({ path: filename, data: await toBase64(blob), directory: Directory.Cache });
        await Share.share({ title: "Your Turnup ticket", files: [written.uri], dialogTitle: "Save your ticket" });
        return;
      }
      const file = new File([blob], filename, { type: "image/png" });
      const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
      const touch = window.matchMedia?.("(pointer: coarse)").matches;
      if (touch && nav.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: "Your Turnup ticket" });
        return;
      }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    } catch (err) {
      // Closing the share sheet isn't an error.
      if ((err as Error)?.name === "AbortError" || /cancel/i.test((err as Error)?.message ?? "")) return;
      setError(apiErrorMessage(err, "Couldn't save the ticket. Take a screenshot of the QR code instead."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      <Button fullWidth loading={busy} onClick={save}><Download size={15} aria-hidden /> Save ticket</Button>
      {error && <p role="alert" className="text-xs text-error text-center">{error}</p>}
    </div>
  );
}
