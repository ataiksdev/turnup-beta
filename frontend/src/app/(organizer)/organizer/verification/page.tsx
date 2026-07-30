"use client";
import { useState } from "react";
import { organizerApi, authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { BadgeCheck, Clock, XCircle, ShieldQuestion } from "lucide-react";

export default function OrganizerVerificationPage() {
  const { token, user, setUser } = useAuthStore();
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const profile = user?.organizer_profile;
  const status = profile?.verification_status ?? "none";

  async function submitRequest() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      await organizerApi.requestVerification(token, note.trim() || undefined);
      const me = await authApi.me(token);
      setUser(me);
      setNote("");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-bg pb-8">
      <TopBar title="Verification" back />

      <div className="px-4 py-4 space-y-4">
        <p className="text-xs text-text-muted">
          A verified badge is a visual trust signal on your profile, events, and communities —
          it doesn't change what you can do. Your events still go through the normal review queue
          either way.
        </p>

        {profile?.is_verified_organizer ? (
          <div className="flex items-start gap-3 p-4 rounded border-2 border-success/40 bg-success/10 shadow-brutal-sm">
            <BadgeCheck size={22} className="text-success shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="text-sm font-black text-text uppercase tracking-wide">You're verified</p>
              <p className="text-xs text-text-muted mt-0.5">
                Your badge is now showing across Turnup.
              </p>
            </div>
          </div>
        ) : status === "pending" ? (
          <div className="flex items-start gap-3 p-4 rounded border-2 border-yellow-500/40 bg-yellow-500/10 shadow-brutal-sm">
            <Clock size={22} className="text-yellow-600 dark:text-yellow-400 shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="text-sm font-black text-text uppercase tracking-wide">Under review</p>
              <p className="text-xs text-text-muted mt-0.5">
                We'll notify you once an admin has reviewed your request.
              </p>
            </div>
          </div>
        ) : (
          <>
            {status === "rejected" && (
              <div className="flex items-start gap-3 p-4 rounded border-2 border-error/40 bg-error/10 shadow-brutal-sm">
                <XCircle size={22} className="text-error shrink-0 mt-0.5" aria-hidden />
                <div>
                  <p className="text-sm font-black text-text uppercase tracking-wide">Request needs changes</p>
                  {profile?.verification_note && (
                    <p className="text-xs text-text-muted mt-0.5">{profile.verification_note}</p>
                  )}
                </div>
              </div>
            )}

            <div className="p-4 rounded border-2 border-border bg-bg-card shadow-brutal-sm space-y-3">
              <div className="flex items-center gap-2">
                <ShieldQuestion size={16} className="text-primary" aria-hidden />
                <span className="text-xs font-black text-text uppercase tracking-widest">
                  {status === "rejected" ? "Re-apply for verification" : "Apply for verification"}
                </span>
              </div>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={1000}
                rows={4}
                placeholder="Tell us about your events or organization (optional)"
                className="w-full rounded border-2 border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
              />
              {error && <p className="text-xs text-error">{error}</p>}
              <Button fullWidth loading={loading} onClick={submitRequest}>
                Submit request
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
