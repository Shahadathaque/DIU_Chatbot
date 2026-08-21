"use client";

import { useEffect, useState, type FormEvent } from "react";
import { EligibilityResult } from "@/components/eligibility/eligibility-result";
import { ClipboardIcon, WarningIcon } from "@/components/ui/icons";
import {
  ApiError,
  checkEligibility,
  getPrograms,
  isMockMode,
} from "@/services/api";
import type {
  EligibilityRequest,
  EligibilityResponse,
  Program,
} from "@/types/api";

const groups: EligibilityRequest["group"][] = [
  "Science",
  "Business Studies",
  "Humanities",
  "Other",
];

const initialForm: EligibilityRequest = {
  program: "",
  ssc_gpa: 4.5,
  hsc_gpa: 4.0,
  group: "Science",
  diploma: false,
};

export function EligibilityForm() {
  const [form, setForm] = useState<EligibilityRequest>(initialForm);
  const [result, setResult] = useState<EligibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [programsLoading, setProgramsLoading] = useState(true);
  const [programsError, setProgramsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadPrograms() {
      try {
        const response = await getPrograms();
        if (cancelled) return;
        setPrograms(response.programs);
        if (response.programs[0]) {
          setForm((current) => ({ ...current, program: response.programs[0].id }));
        }
        setProgramsError(null);
      } catch (requestError) {
        if (cancelled) return;
        setProgramsError(
          requestError instanceof ApiError
            ? requestError.message
            : "Could not load programs. Please try again.",
        );
      } finally {
        if (!cancelled) setProgramsLoading(false);
      }
    }

    void loadPrograms();
    return () => {
      cancelled = true;
    };
  }, []);

  function updateField<K extends keyof EligibilityRequest>(
    key: K,
    value: EligibilityRequest[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await checkEligibility(form);
      setResult(response);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Eligibility check failed. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="page-shell grid gap-8 py-8 lg:grid-cols-[1.05fr_.95fr] lg:py-12">
      <section className="rounded-[1.5rem] border border-line bg-white p-6 shadow-soft sm:p-8">
        <div className="flex items-start gap-4">
          <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">
            <ClipboardIcon size={22} />
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">
              Eligibility checker
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              Submit your academic profile. Eligibility is determined only by collected,
              explicit rules; missing evidence is reported instead of guessed.
            </p>
          </div>
        </div>

        <form className="mt-8 grid gap-5" onSubmit={onSubmit}>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label
                className="mb-2 block text-xs font-bold uppercase tracking-[0.08em] text-muted"
                htmlFor="program"
              >
                Desired program
              </label>
              <select
                className="h-12 w-full rounded-xl border border-line bg-canvas px-4 text-sm font-semibold text-ink disabled:opacity-60"
                disabled={programsLoading}
                id="program"
                onChange={(event) => updateField("program", event.target.value)}
                value={form.program}
              >
                {programsLoading ? (
                  <option value="">Loading programs...</option>
                ) : programs.length === 0 ? (
                  <option value="">No programs available</option>
                ) : (
                  programs.map((program) => (
                    <option key={program.id} value={program.id}>
                      {program.name}
                    </option>
                  ))
                )}
              </select>
              {programsError ? (
                <p className="mt-2 text-xs leading-5 text-red-700" role="alert">
                  {programsError}
                </p>
              ) : null}
            </div>

            <div>
              <label
                className="mb-2 block text-xs font-bold uppercase tracking-[0.08em] text-muted"
                htmlFor="group"
              >
                Academic group
              </label>
              <select
                className="h-12 w-full rounded-xl border border-line bg-canvas px-4 text-sm font-semibold text-ink"
                id="group"
                onChange={(event) =>
                  updateField("group", event.target.value as EligibilityRequest["group"])
                }
                value={form.group}
              >
                {groups.map((group) => (
                  <option key={group} value={group}>
                    {group}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <label
                className="mb-2 block text-xs font-bold uppercase tracking-[0.08em] text-muted"
                htmlFor="ssc_gpa"
              >
                SSC GPA
              </label>
              <input
                className="h-12 w-full rounded-xl border border-line bg-canvas px-4 text-sm font-semibold text-ink"
                id="ssc_gpa"
                max={5}
                min={0}
                onChange={(event) => updateField("ssc_gpa", Number(event.target.value))}
                required
                step={0.01}
                type="number"
                value={form.ssc_gpa}
              />
            </div>

            <div>
              <label
                className="mb-2 block text-xs font-bold uppercase tracking-[0.08em] text-muted"
                htmlFor="hsc_gpa"
              >
                HSC GPA
              </label>
              <input
                className="h-12 w-full rounded-xl border border-line bg-canvas px-4 text-sm font-semibold text-ink"
                id="hsc_gpa"
                max={5}
                min={0}
                onChange={(event) => updateField("hsc_gpa", Number(event.target.value))}
                required
                step={0.01}
                type="number"
                value={form.hsc_gpa}
              />
            </div>
          </div>

          <label className="flex items-center gap-3 rounded-xl border border-line bg-canvas px-4 py-3 text-sm font-semibold text-ink">
            <input
              checked={form.diploma}
              className="size-4 accent-[var(--brand)]"
              onChange={(event) => updateField("diploma", event.target.checked)}
              type="checkbox"
            />
            I am applying as a diploma student
          </label>

          <button
            className="inline-flex min-h-12 items-center justify-center rounded-xl bg-brand px-6 text-sm font-bold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={isLoading || programsLoading || !form.program}
            type="submit"
          >
            {isLoading ? "Checking eligibility..." : "Check eligibility"}
          </button>

          <p className="text-xs text-muted">
            Mode: {isMockMode ? "Demo / mock API" : "Live research API"}
          </p>
        </form>
      </section>

      <section className="space-y-4">
        {error ? (
          <div
            className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-900"
            role="alert"
          >
            <div className="flex items-start gap-3">
              <WarningIcon className="mt-0.5 shrink-0" size={18} />
              <div>
                <p className="font-bold">Eligibility check unavailable</p>
                <p className="mt-1 leading-6 text-red-800">{error}</p>
              </div>
            </div>
          </div>
        ) : null}

        {result ? (
          <EligibilityResult result={result} />
        ) : !error ? (
          <div className="rounded-[1.5rem] border border-dashed border-line bg-white/70 p-8 text-center">
            <p className="text-sm font-bold text-ink">Results appear here</p>
            <p className="mt-2 text-sm leading-6 text-muted">
              After you submit, the backend response will show Eligible, Not Eligible, or
              Insufficient Information — with the provided reason and source.
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
