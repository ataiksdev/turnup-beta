"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ClipboardList, Download, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiErrorMessage, eventsApi, type QuestionKind, type RegistrationQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

const KINDS: [QuestionKind, string][] = [
  ["text", "Short answer"], ["long_text", "Paragraph"], ["single_choice", "One choice"],
  ["multi_choice", "Several choices"], ["checkbox", "Tick box (e.g. agree to terms)"],
];
const field = "h-9 rounded border-2 border-border bg-bg px-2 text-sm text-text";

function csvCell(v: string): string {
  // Quote, and stop spreadsheet apps from running an answer as a formula.
  const safe = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
  return `"${safe.replace(/"/g, '""')}"`;
}

/** Questions everyone answers when they register, and what they answered. */
export function RegistrationQuestionsManager({ eventId, eventTitle }: { eventId: string; eventTitle?: string }) {
  const { token } = useAuthStore();
  const qc = useQueryClient();
  const key = ["questions", eventId];
  const { data: questions } = useQuery({
    queryKey: key, queryFn: () => eventsApi.questions(eventId), enabled: !!eventId,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ["registrations", eventId] });
  };

  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<QuestionKind>("text");
  const [options, setOptions] = useState("");
  const [required, setRequired] = useState(false);
  const [error, setError] = useState("");
  const [showAnswers, setShowAnswers] = useState(false);
  const isChoice = kind === "single_choice" || kind === "multi_choice";

  const create = useMutation({
    mutationFn: () => eventsApi.createQuestion(token!, eventId, {
      label: label.trim(), kind, required,
      options: isChoice ? options.split("\n").map((o) => o.trim()).filter(Boolean) : null,
    }),
    onSuccess: () => { setLabel(""); setOptions(""); setRequired(false); setError(""); refresh(); },
    onError: (err) => setError(apiErrorMessage(err, "Couldn't add the question.")),
  });
  const update = useMutation({
    mutationFn: ({ q, data }: { q: RegistrationQuestion; data: Partial<RegistrationQuestion> }) =>
      eventsApi.updateQuestion(token!, eventId, q.id, data),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (q: RegistrationQuestion) => eventsApi.deleteQuestion(token!, eventId, q.id),
    onSuccess: refresh,
  });

  async function move(index: number, by: -1 | 1) {
    const list = questions ?? [];
    const other = list[index + by];
    if (!other) return;
    // Renumber the whole list so positions are distinct, then swap the two.
    const order = list.map((q) => q.id);
    [order[index], order[index + by]] = [order[index + by], order[index]];
    await Promise.all(order.map((id, i) => {
      const q = list.find((x) => x.id === id)!;
      return q.position === i ? null : eventsApi.updateQuestion(token!, eventId, id, { position: i });
    }));
    refresh();
  }

  const { data: regs } = useQuery({
    queryKey: ["registrations", eventId],
    queryFn: () => eventsApi.registrations(token!, eventId),
    enabled: !!token && !!eventId && showAnswers,
  });

  function downloadCsv() {
    if (!regs) return;
    const header = ["Name", "Username", "Email", "Registered with", ...regs.questions.map((q) => q.label)];
    const lines = regs.rows.map((r) => [
      r.name, r.username ?? "", r.email ?? "", r.status === "ticket" ? "Ticket" : "RSVP",
      ...regs.questions.map((q) => r.answers[q.id] ?? ""),
    ]);
    const csv = [header, ...lines].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    a.download = `${(eventTitle || "event").replace(/[^\w-]+/g, "-").slice(0, 50)}-registrations.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-bold text-text-secondary uppercase tracking-wide flex items-center gap-1.5">
        <ClipboardList size={13} aria-hidden /> Registration questions
      </p>
      <p className="text-[11px] text-text-muted">
        Asked when someone gets a ticket or RSVPs &quot;going&quot;. Name and email are collected already.
      </p>

      {questions?.map((q, i) => (
        <div key={q.id} className="flex items-start gap-2 p-2 rounded border-2 border-border bg-bg-card text-sm">
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-text">{q.label}{q.required && <span className="text-error"> *</span>}</p>
            <p className="text-[11px] text-text-muted">
              {KINDS.find(([k]) => k === q.kind)?.[1]}
              {q.options?.length ? `: ${q.options.join(", ")}` : ""}
            </p>
          </div>
          <label className="flex items-center gap-1 text-[11px] text-text-muted shrink-0 cursor-pointer">
            <input type="checkbox" checked={q.required} className="accent-primary"
              onChange={(e) => update.mutate({ q, data: { required: e.target.checked } })} /> Required
          </label>
          <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}
            className="p-1 rounded text-text-muted hover:bg-bg-elevated disabled:opacity-30"><ArrowUp size={14} aria-hidden /></button>
          <button type="button" aria-label="Move down" disabled={i === (questions?.length ?? 0) - 1} onClick={() => move(i, 1)}
            className="p-1 rounded text-text-muted hover:bg-bg-elevated disabled:opacity-30"><ArrowDown size={14} aria-hidden /></button>
          <button type="button" aria-label={`Remove "${q.label}"`}
            onClick={() => { if (confirm("Remove this question? Answers already given are kept.")) remove.mutate(q); }}
            className="p-1 rounded text-text-muted hover:text-error hover:bg-bg-elevated"><Trash2 size={14} aria-hidden /></button>
        </div>
      ))}

      <form className="space-y-2 p-2 rounded border-2 border-dashed border-border"
        onSubmit={(e) => { e.preventDefault(); setError(""); create.mutate(); }}>
        <input required maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. What company do you work for?" aria-label="Question"
          className={cn(field, "w-full")} />
        <div className="flex gap-2 items-center">
          <select value={kind} onChange={(e) => setKind(e.target.value as QuestionKind)} aria-label="Answer type"
            className={cn(field, "flex-1")}>
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-text cursor-pointer">
            <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} className="accent-primary" />
            Required
          </label>
        </div>
        {isChoice && (
          <textarea required rows={3} value={options} onChange={(e) => setOptions(e.target.value)}
            placeholder={"One choice per line\nVegan\nHalal\nNo preference"} aria-label="Choices"
            className="w-full rounded border-2 border-border bg-bg px-2 py-1.5 text-sm text-text resize-none" />
        )}
        <Button type="submit" size="sm" loading={create.isPending}>Add question</Button>
        {error && <p className="text-xs text-error">{error}</p>}
      </form>

      <div className="pt-1">
        <button type="button" onClick={() => setShowAnswers((v) => !v)} aria-expanded={showAnswers}
          className="text-xs font-bold text-primary hover:underline">
          {showAnswers ? "Hide answers" : "See answers"}
        </button>
        {showAnswers && regs && (
          <div className="mt-2 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs text-text-muted">{regs.rows.length} registered</p>
              {regs.rows.length > 0 && (
                <Button size="xs" variant="secondary" onClick={downloadCsv}><Download size={12} aria-hidden /> CSV</Button>
              )}
            </div>
            {regs.rows.length > 0 && regs.questions.length > 0 && (
              <div className="overflow-x-auto rounded border-2 border-border">
                <table className="w-full text-xs">
                  <thead className="bg-bg-elevated text-text-secondary">
                    <tr>
                      <th className="text-left px-2 py-1.5 font-bold">Name</th>
                      {regs.questions.map((q) => <th key={q.id} className="text-left px-2 py-1.5 font-bold whitespace-nowrap">{q.label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {regs.rows.slice(0, 100).map((r) => (
                      <tr key={r.user_id} className="border-t border-border">
                        <td className="px-2 py-1.5 text-text whitespace-nowrap">{r.name}</td>
                        {regs.questions.map((q) => <td key={q.id} className="px-2 py-1.5 text-text-secondary">{r.answers[q.id] ?? "—"}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {regs.rows.length > 100 && <p className="px-2 py-1.5 text-[11px] text-text-muted">Showing 100. Download the CSV for everyone.</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
