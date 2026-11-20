"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { eventsApi, type CheckInResult } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  Camera, CameraOff, CheckCircle2, XCircle, Keyboard, RefreshCw, Users,
} from "lucide-react";
import { format } from "date-fns";
import { useRouteParam } from "@/lib/useRouteParam";
import { plusApi } from "@/lib/marketplace";

// ── Types ─────────────────────────────────────────────────────────────────────

type ScanState = "idle" | "scanning" | "choosing" | "success" | "error";

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CheckInPage() {
  const eventId = useRouteParam("id");
  const { token } = useAuthStore();

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);

  const [camEnabled, setCamEnabled] = useState(false);
  const [camError, setCamError] = useState("");
  const [manualCode, setManualCode] = useState("");
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [lastResult, setLastResult] = useState<CheckInResult | null>(null);
  const [lastError, setLastError] = useState("");
  const [showManual, setShowManual] = useState(false);
  // A ticket for several people with more than one still to come in: staff pick how many.
  const [choice, setChoice] = useState<CheckInResult | null>(null);
  const [admitN, setAdmitN] = useState(1);
  const qc = useQueryClient();

  // Debounce: don't re-scan same code within 3s
  const lastCodeRef = useRef("");
  const lastCodeTimeRef = useRef(0);
  // The camera loop runs outside React renders, so it reads the current state through a ref
  // (reading state directly gave it the values from the first render).
  const busyRef = useRef(false);
  useEffect(() => { busyRef.current = scanState !== "idle"; }, [scanState]);

  // Live count from the server, shared by every phone scanning this event.
  const stats = useQuery({
    queryKey: ["checkin-stats", eventId],
    queryFn: () => eventsApi.checkInStats(token!, eventId),
    enabled: !!token && !!eventId,
    refetchInterval: 5000,
  });

  const checkInMutation = useMutation({
    mutationFn: ({ code, admit }: { code: string; admit?: number }) => eventsApi.checkIn(token!, eventId, code, admit),
    onSuccess: (data) => {
      if (data.needs_choice) {
        setChoice(data);
        setAdmitN(data.remaining ?? 1);
        setScanState("choosing");
        return;
      }
      setChoice(null);
      setScanState("success");
      setLastResult(data);
      setLastError("");
      qc.invalidateQueries({ queryKey: ["checkin-stats", eventId] });
      setTimeout(() => setScanState("idle"), 3000);
    },
    onError: (e: any) => {
      setChoice(null);
      setScanState("error");
      setLastError(e.message ?? "Check-in failed");
      setTimeout(() => setScanState("idle"), 3000);
    },
  });

  // ── Camera logic ──────────────────────────────────────────────────────────

  const stopCamera = useCallback(() => {
    cancelAnimationFrame(animRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamEnabled(false);
  }, []);

  const processFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      animRef.current = requestAnimationFrame(processFrame);
      return;
    }
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) { animRef.current = requestAnimationFrame(processFrame); return; }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    // Dynamically import jsQR to keep initial bundle small
    import("jsqr").then(({ default: jsQR }) => {
      const result = jsQR(imageData.data, imageData.width, imageData.height);
      if (result?.data) {
        const now = Date.now();
        if (result.data !== lastCodeRef.current || now - lastCodeTimeRef.current > 3000) {
          lastCodeRef.current = result.data;
          lastCodeTimeRef.current = now;
          handleScanRef.current(result.data);
        }
      }
    }).catch(() => {});

    animRef.current = requestAnimationFrame(processFrame);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const startCamera = useCallback(async () => {
    setCamError("");
    // getUserMedia requires a secure context
    if (!navigator.mediaDevices?.getUserMedia) {
      setCamError("Camera requires HTTPS. Use manual entry below.");
      setShowManual(true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCamEnabled(true);
      animRef.current = requestAnimationFrame(processFrame);
    } catch {
      setCamError("Could not access camera. Check permissions or use manual entry.");
      setShowManual(true);
    }
  }, [processFrame]);

  // Stop camera when leaving
  useEffect(() => () => stopCamera(), [stopCamera]);

  // ── Scan handler ──────────────────────────────────────────────────────────

  function handleScan(raw: string) {
    if (busyRef.current) return;
    let code = raw.trim();
    // QR value is JSON: {"code":"...", "order":"...", "event":"..."}
    try {
      const parsed = JSON.parse(raw);
      if (parsed.code) code = parsed.code;
    } catch {
      // not JSON — treat raw value as the ticket code directly
    }
    if (!code) return;
    busyRef.current = true;
    setScanState("scanning");
    checkInMutation.mutate({ code });
  }
  const handleScanRef = useRef(handleScan);
  handleScanRef.current = handleScan;

  function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    const code = manualCode.trim();
    if (!code) return;
    setManualCode("");
    handleScan(code);
  }

  // ── Overlay color ─────────────────────────────────────────────────────────

  const overlayColor =
    scanState === "success" ? "border-success bg-success/10" :
    scanState === "error"   ? "border-error bg-error/10" :
    scanState === "scanning" ? "border-primary/60 bg-primary/5" :
    "border-white/30 bg-transparent";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col min-h-screen bg-bg pb-8">
      <TopBar back title="Check-in Scanner" />

      {/* Camera viewfinder */}
      <div className="relative w-full bg-black" style={{ aspectRatio: "4/3", maxHeight: "60vw" }}>
        <video
          ref={videoRef}
          playsInline
          muted
          className={cn("w-full h-full object-cover", !camEnabled && "hidden")}
        />
        <canvas ref={canvasRef} className="hidden" />

        {/* Scan area overlay */}
        {camEnabled && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className={cn(
              "w-48 h-48 border-4 rounded-xl transition-all duration-200",
              overlayColor,
            )} />
          </div>
        )}

        {/* Idle camera placeholder */}
        {!camEnabled && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg-elevated">
            {camError ? (
              <>
                <CameraOff size={36} className="text-error/60" />
                <p className="text-xs text-error/80 text-center px-6">{camError}</p>
              </>
            ) : (
              <>
                <Camera size={36} className="text-text-muted" />
                <p className="text-xs text-text-muted">Tap to start scanner</p>
              </>
            )}
          </div>
        )}

        {/* Result overlay badge */}
        {(scanState === "success" || scanState === "error") && (
          <div className={cn(
            "absolute bottom-3 left-3 right-3 flex items-start gap-2 p-3 rounded-xl border-2 backdrop-blur-sm",
            scanState === "success" ? "border-success/60 bg-success/20" : "border-error/60 bg-error/20",
          )}>
            {scanState === "success" ? (
              <>
                <CheckCircle2 size={18} className="text-success shrink-0 mt-0.5" />
                <div>
                  {lastResult?.fast_lane && (
                    <p className="mb-1 inline-block px-2 py-0.5 rounded bg-primary text-on-primary text-lg font-black tracking-widest">
                      FAST LANE
                    </p>
                  )}
                  <p className="text-sm font-black text-white">{lastResult?.attendee_name}</p>
                  <p className="text-xs text-white/70">
                    {lastResult && lastResult.quantity > 1
                      ? `Admit ${lastResult.admitted_now} · ${lastResult.admitted_count} of ${lastResult.quantity} in · ${lastResult.tier_name}`
                      : `${lastResult?.tier_name} × ${lastResult?.quantity}`}
                  </p>
                </div>
              </>
            ) : (
              <>
                <XCircle size={18} className="text-error shrink-0 mt-0.5" />
                <p className="text-sm font-bold text-white">{lastError}</p>
              </>
            )}
          </div>
        )}
      </div>

      {/* How many of this ticket's people are at the door? */}
      {choice && (
        <div className="mx-4 mt-3 p-4 rounded border-2 border-primary bg-bg-card space-y-3" role="dialog" aria-label="How many are here?">
          {choice.fast_lane && <p className="inline-block px-2 py-0.5 rounded bg-primary text-on-primary font-black tracking-widest">FAST LANE</p>}
          <div>
            <p className="text-base font-black text-text">{choice.attendee_name}</p>
            <p className="text-xs text-text-secondary">{choice.tier_name} · {choice.remaining} of {choice.quantity} still to come in</p>
          </div>
          <p className="text-xs font-bold text-text">How many are here now?</p>
          <div className="flex items-center gap-3">
            <button className="w-10 h-10 rounded border-2 border-border text-lg font-black text-text disabled:opacity-40" aria-label="One fewer"
              disabled={admitN <= 1} onClick={() => setAdmitN((n) => n - 1)}>−</button>
            <span className="text-2xl font-black text-text w-8 text-center" aria-live="polite">{admitN}</span>
            <button className="w-10 h-10 rounded border-2 border-border text-lg font-black text-text disabled:opacity-40" aria-label="One more"
              disabled={admitN >= (choice.remaining ?? 1)} onClick={() => setAdmitN((n) => n + 1)}>+</button>
            <Button className="flex-1" loading={checkInMutation.isPending}
              onClick={() => checkInMutation.mutate({ code: choice.ticket_code, admit: admitN })}>
              Admit {admitN}
            </Button>
          </div>
          <button className="text-xs font-bold text-text-muted underline" onClick={() => { setChoice(null); setScanState("idle"); }}>Cancel</button>
        </div>
      )}

      {/* Camera controls */}
      <div className="px-4 pt-3 flex gap-2">
        {!camEnabled ? (
          <Button size="sm" onClick={startCamera} className="flex-1">
            <Camera size={14} /> Start Camera
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={stopCamera} className="flex-1">
            <CameraOff size={14} /> Stop Camera
          </Button>
        )}
        <button
          onClick={() => setShowManual((v) => !v)}
          className={cn(
            "px-3 py-2 rounded border-2 text-xs font-black uppercase tracking-widest transition-colors",
            showManual ? "border-primary bg-primary/10 text-primary" : "border-border text-text-muted hover:border-border-strong",
          )}
        >
          <Keyboard size={14} />
        </button>
      </div>

      {/* Manual entry */}
      {showManual && (
        <form onSubmit={handleManualSubmit} className="px-4 pt-3 flex gap-2">
          <input
            type="text"
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value)}
            placeholder="Paste or type ticket code…"
            className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary font-mono"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
          />
          <Button
            type="submit"
            size="sm"
            loading={checkInMutation.isPending}
            disabled={!manualCode.trim()}
          >
            <RefreshCw size={14} /> Check In
          </Button>
        </form>
      )}

      {/* Turnup+ deal codes */}
      <DealCodeCheck eventId={eventId} />

      {/* Live door count and latest check-ins, from every phone scanning this event */}
      <div className="px-4 pt-5">
        <div className="flex items-end justify-between mb-3">
          <div className="flex items-center gap-2">
            <Users size={14} className="text-text-muted" />
            <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">At the door (all scanners)</p>
          </div>
          {stats.data && (
            <p className="text-right" aria-live="polite">
              <span className="text-2xl font-black text-text">{stats.data.people_in}</span>
              <span className="text-sm font-bold text-text-muted"> / {stats.data.people_expected} in</span>
            </p>
          )}
        </div>
        {stats.data && stats.data.people_expected > 0 && (
          <div className="h-2 rounded-full bg-bg-elevated overflow-hidden mb-3">
            <div className="h-full bg-success transition-all" style={{ width: `${Math.round((stats.data.people_in / stats.data.people_expected) * 100)}%` }} />
          </div>
        )}

        {!stats.data?.recent.length ? (
          <p className="text-xs text-text-muted text-center py-8">
            Scanned tickets will appear here
          </p>
        ) : (
          <div className="space-y-2">
            {stats.data.recent.map((r) => (
              <div key={r.order_id} className="flex items-center justify-between p-3 rounded border-2 border-border bg-bg-card">
                <div>
                  <p className="text-sm font-bold text-text">{r.name}</p>
                  <p className="text-xs text-text-muted">{r.tier} · {r.admitted} of {r.quantity} in</p>
                </div>
                <div className="text-right">
                  <p className="text-xs font-bold text-success">{format(new Date(r.first_in), "h:mm a")}</p>
                  <p className="text-[10px] font-mono text-text-disabled">{r.code}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


function DealCodeCheck({ eventId }: { eventId: string }) {
  const { token } = useAuthStore();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const redeem = useMutation({
    mutationFn: () => plusApi.redeemEventDeal(token!, eventId, code.trim()),
    onSuccess: (r) => {
      setResult(r.ok ? { ok: true, text: `${r.deal}: valid for ${r.member}` }
        : { ok: false, text: r.reason === "already_used" ? "Already used" : r.reason === "membership_lapsed" ? "Membership has lapsed" : "Expired" });
      setCode("");
    },
    onError: (e: any) => setResult({ ok: false, text: e.message ?? "Not found" }),
  });
  return (
    <form className="px-4 pt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (code.trim()) redeem.mutate(); }}>
      <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="Turnup+ deal code"
        aria-label="Turnup+ deal code" maxLength={12}
        className="flex-1 bg-bg-card border-2 border-border rounded px-3 py-2 text-sm text-text font-mono uppercase" />
      <Button type="submit" size="sm" variant="secondary" loading={redeem.isPending} disabled={!code.trim()}>Check deal</Button>
      {result && <p role="status" className={cn("self-center text-xs font-bold", result.ok ? "text-success" : "text-error")}>{result.text}</p>}
    </form>
  );
}
