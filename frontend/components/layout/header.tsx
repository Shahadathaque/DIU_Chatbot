"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { MenuIcon, SparkleIcon, XIcon } from "@/components/ui/icons";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Ask AI" },
  { href: "/eligibility", label: "Eligibility" },
  { href: "/programs", label: "Programs" },
  { href: "/blog", label: "Guides" },
];

export function Header() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line/80 bg-white/90 backdrop-blur-xl">
      <div className="page-shell flex h-[72px] items-center justify-between">
        <Link
          className="flex items-center gap-3 rounded-lg"
          href="/"
          onClick={() => setIsOpen(false)}
        >
          <span className="grid size-10 place-items-center rounded-xl bg-brand text-white shadow-[0_7px_18px_rgba(8,120,63,0.24)]">
            <SparkleIcon size={20} />
          </span>
          <span>
            <span className="block text-[15px] font-bold tracking-[-0.02em] text-ink">
              DIU Admission AI
            </span>
            <span className="hidden text-[11px] font-medium text-muted sm:block">
              Verified-source guidance
            </span>
          </span>
        </Link>

        <nav aria-label="Primary navigation" className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                  active
                    ? "bg-brand-soft text-brand-dark"
                    : "text-muted hover:bg-canvas hover:text-ink"
                }`}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <a
          className="hidden rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(8,120,63,0.18)] transition hover:bg-brand-dark lg:inline-flex"
          href="https://daffodilvarsity.edu.bd/"
          rel="noopener noreferrer"
          target="_blank"
        >
          Official DIU website
        </a>

        <button
          aria-expanded={isOpen}
          aria-label={isOpen ? "Close navigation menu" : "Open navigation menu"}
          className="grid size-11 place-items-center rounded-xl border border-line bg-white text-ink md:hidden"
          onClick={() => setIsOpen((value) => !value)}
          type="button"
        >
          {isOpen ? <XIcon /> : <MenuIcon />}
        </button>
      </div>

      {isOpen ? (
        <nav
          aria-label="Mobile navigation"
          className="page-shell border-t border-line py-3 md:hidden"
        >
          <div className="grid gap-1">
            {navItems.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={`rounded-xl px-4 py-3 text-sm font-semibold ${
                    active ? "bg-brand-soft text-brand-dark" : "text-muted"
                  }`}
                  href={item.href}
                  key={item.href}
                  onClick={() => setIsOpen(false)}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
