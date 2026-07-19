"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { eventsApi, type CheckInResult } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  Camera, CameraOff, CheckCircle2, XCircle, Keyboard, RefreshCw, Users,
} from "lucide-react";
import { format } from "date-fns";

// ── Types ─────────────────────────────────────────────────────────────────────

type ScanState = "idle" | "scanning" | "success" | "error";

interface ScanRecord {
  name: string;
  tier: string;
  qty: number;
  time: string;
  code: string;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CheckInPage() {
  const { id: eventId } = useParams<{ id: string }>();
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
  const [recentScans, setRecentScans] = useState<ScanRecord[]>([]);
  const [showManual, setShowManual] = useState(false);

  // Debounce: don't re-scan same code within 3s
  const lastCodeRef = useRef("");
  const lastCodeTimeRef = useRef(0);

  const checkInMutation = useMutation({
    mutationFn: (code: string) => eventsApi.checkIn(token!, eventId, code),
    onSuccess: (data) => {
      setScanState("success");
      setLastResult(data);
      setLastError("");
      setRecentScans((prev) => [
        {
          name: data.attendee_name,
          tier: data.tier_name,
          qty: data.quantity,
          time: format(new Date(data.checked_in_at), "h:mm a"),
          code: data.ticket_code.slice(0, 8).toUpperCase(),
        },
        ...prev.slice(0, 19),
      ]);
      setTimeout(() => setScanState("idle"), 3000);
    },
    onError: (e: any) => {
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
          handleScan(result.data);
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
    if (checkInMutation.isPending || scanState !== "idle") return;
    let code = raw.trim();
    // QR value is JSON: {"code":"...", "order":"...", "event":"..."}
    try {
      const parsed = JSON.parse(raw);
      if (parsed.code) code = parsed.code;
    } catch {
      // not JSON — treat raw value as the ticket code directly
    }
    if (!code) return;
    setScanState("scanning");
    checkInMutation.mutate(code);
  }

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
        {scanState !== "idle" && scanState !== "scanning" && (
          <div className={cn(
            "absolute bottom-3 left-3 right-3 flex items-start gap-2 p-3 rounded-xl border-2 backdrop-blur-sm",
            scanState === "success" ? "border-success/60 bg-success/20" : "border-error/60 bg-error/20",
          )}>
            {scanState === "success" ? (
              <>
                <CheckCircle2 size={18} className="text-success shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-black text-white">{lastResult?.attendee_name}</p>
                  <p className="text-xs text-white/70">{lastResult?.tier_name} × {lastResult?.quantity}</p>
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

      {/* Scan log */}
      <div className="px-4 pt-5">
        <div className="flex items-center gap-2 mb-3">
          <Users size={14} className="text-text-muted" />
          <p className="text-[10px] font-black text-text-muted uppercase tracking-widest">
            Checked In · {recentScans.length}
          </p>
        </div>

        {recentScans.length === 0 ? (
          <p className="text-xs text-text-muted text-center py-8">
            Scanned tickets will appear here
          </p>
        ) : (
          <div className="space-y-2">
            {recentScans.map((r, i) => (
              <div
                key={`${r.code}-${i}`}
                className="flex items-center justify-between p-3 rounded border-2 border-border bg-bg-card"
              >
                <div>
                  <p className="text-sm font-bold text-text">{r.name}</p>
                  <p className="text-xs text-text-muted">{r.tier} × {r.qty}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs font-bold text-success">{r.time}</p>
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
