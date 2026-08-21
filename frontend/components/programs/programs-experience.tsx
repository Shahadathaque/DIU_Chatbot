"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ProgramCard } from "@/components/programs/program-card";
import { GraduationIcon, SearchIcon, WarningIcon } from "@/components/ui/icons";
import { ApiError, getPrograms, isMockMode } from "@/services/api";
import type { Program } from "@/types/api";

export function ProgramsExperience() {
  const [programs, setPrograms] = useState<Program[]>([]);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await getPrograms();
        if (cancelled) return;
        setPrograms(response.programs);
        setError(null);
      } catch (requestError) {
        if (cancelled) return;
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : "Could not load programs. Please try again.",
        );
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  function refresh() {
    setIsLoading(true);
    setError(null);
    setReloadToken((value) => value + 1);
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return programs;
    return programs.filter((program) =>
      [program.name, program.faculty, program.degree]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(needle)),
    );
  }, [programs, query]);

  return (
    <div className="page-shell py-8 sm:py-12">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <span className="eyebrow">
            <GraduationIcon size={14} /> Program directory
          </span>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
            Explore DIU programs
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted sm:text-base">
            Browse admission-related programs in the project&apos;s verified-source catalog.
            Program information can change, so confirm important details with DIU.
          </p>
          <Link className="mt-3 inline-flex text-sm font-bold text-brand hover:text-brand-dark" href="/blog/diu-programs-guide">
            Read the program selection guide →
          </Link>
        </div>
        <p className="text-xs font-semibold text-muted">
          {isMockMode ? "Demo program catalog" : "Verified-source program catalog"}
        </p>
      </div>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative block flex-1" htmlFor="program-search">
          <span className="sr-only">Search programs</span>
          <SearchIcon
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted"
            size={18}
          />
          <input
            className="h-12 w-full rounded-xl border border-line bg-white pl-11 pr-4 text-sm font-semibold text-ink shadow-sm"
            id="program-search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by program, faculty, or degree"
            type="search"
            value={query}
          />
        </label>
        <button
          className="inline-flex h-12 items-center justify-center rounded-xl border border-line bg-white px-5 text-sm font-bold text-ink hover:bg-canvas"
          onClick={refresh}
          type="button"
        >
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              className="h-56 animate-pulse rounded-2xl border border-line bg-white"
              key={index}
            />
          ))}
        </div>
      ) : null}

      {error ? (
        <div
          className="mt-10 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-900"
          role="alert"
        >
          <div className="flex items-start gap-3">
            <WarningIcon className="mt-0.5 shrink-0" size={18} />
            <div>
              <p className="font-bold">Programs unavailable</p>
              <p className="mt-1 leading-6 text-red-800">{error}</p>
              <button
                className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-bold hover:bg-red-100"
                onClick={refresh}
                type="button"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {!isLoading && !error && filtered.length === 0 ? (
        <div className="mt-10 rounded-[1.5rem] border border-dashed border-line bg-white p-10 text-center">
          <p className="text-sm font-bold text-ink">No programs found</p>
          <p className="mt-2 text-sm leading-6 text-muted">
            {programs.length === 0
              ? "The backend returned an empty program list."
              : "Try a different search term."}
          </p>
        </div>
      ) : null}

      {!isLoading && !error && filtered.length > 0 ? (
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((program) => (
            <ProgramCard key={program.id} program={program} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
