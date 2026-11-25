"use client";
import type { RegistrationAnswers, RegistrationQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputClass =
  "w-full rounded border-2 border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted " +
  "focus:outline-none focus:border-primary";

function isBlank(v: RegistrationAnswers[string] | undefined): boolean {
  if (v === undefined || v === null || v === false) return true;
  if (Array.isArray(v)) return v.length === 0;
  return typeof v === "string" && v.trim() === "";
}

/** The first required question left blank (the API checks too; this saves a round trip). */
export function firstMissingAnswer(
  questions: RegistrationQuestion[] | undefined, answers: RegistrationAnswers,
): RegistrationQuestion | undefined {
  return questions?.find((q) => q.required && isBlank(answers[q.id]));
}

/** The organizer's registration questions, as form fields. */
export function RegistrationFields({ questions, answers, onChange, missingId }: {
  questions: RegistrationQuestion[];
  answers: RegistrationAnswers;
  onChange: (answers: RegistrationAnswers) => void;
  /** A required question to highlight after a submit attempt. */
  missingId?: string | null;
}) {
  const set = (id: string, v: RegistrationAnswers[string]) => onChange({ ...answers, [id]: v });

  return (
    <div className="space-y-4">
      {questions.map((q) => {
        const id = `rq-${q.id}`;
        const value = answers[q.id];
        const invalid = missingId === q.id;
        const label = (
          <span className="text-sm font-semibold text-text">
            {q.label}{q.required && <span className="text-error" aria-hidden> *</span>}
          </span>
        );
        const help = q.help_text && <span className="block text-xs text-text-muted mt-0.5">{q.help_text}</span>;

        if (q.kind === "checkbox") {
          return (
            <label key={q.id} className={cn("flex items-start gap-2.5 cursor-pointer", invalid && "text-error")}>
              <input type="checkbox" checked={value === true} aria-required={q.required}
                aria-invalid={invalid || undefined}
                onChange={(e) => set(q.id, e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-primary" />
              <span>{label}{help}</span>
            </label>
          );
        }

        if (q.kind === "single_choice" || q.kind === "multi_choice") {
          const multi = q.kind === "multi_choice";
          const chosen = multi ? (Array.isArray(value) ? value : []) : (typeof value === "string" ? value : "");
          return (
            <fieldset key={q.id} aria-required={q.required} aria-invalid={invalid || undefined}>
              <legend>{label}{help}</legend>
              <div className="flex flex-wrap gap-2 mt-2">
                {(q.options ?? []).map((opt) => {
                  const on = multi ? (chosen as string[]).includes(opt) : chosen === opt;
                  return (
                    <button key={opt} type="button" aria-pressed={on}
                      onClick={() => {
                        if (multi) {
                          const list = chosen as string[];
                          set(q.id, on ? list.filter((x) => x !== opt) : [...list, opt]);
                        } else {
                          set(q.id, on ? null : opt);
                        }
                      }}
                      className={cn(
                        "px-3 py-1.5 rounded border-2 text-sm font-semibold transition-colors",
                        on ? "border-primary bg-primary/10 text-primary" : "border-border text-text hover:border-border-strong",
                        invalid && !on && "border-error/60",
                      )}>
                      {opt}
                    </button>
                  );
                })}
              </div>
              {multi && <span className="block text-[11px] text-text-muted mt-1">Choose any that apply</span>}
            </fieldset>
          );
        }

        return (
          <div key={q.id}>
            <label htmlFor={id} className="block mb-1.5">{label}{help}</label>
            {q.kind === "long_text" ? (
              <textarea id={id} rows={3} maxLength={2000} value={typeof value === "string" ? value : ""}
                aria-required={q.required} aria-invalid={invalid || undefined}
                onChange={(e) => set(q.id, e.target.value)}
                className={cn(inputClass, "resize-none", invalid && "border-error")} />
            ) : (
              <input id={id} maxLength={2000} value={typeof value === "string" ? value : ""}
                aria-required={q.required} aria-invalid={invalid || undefined}
                onChange={(e) => set(q.id, e.target.value)}
                className={cn(inputClass, "h-10", invalid && "border-error")} />
            )}
          </div>
        );
      })}
    </div>
  );
}
