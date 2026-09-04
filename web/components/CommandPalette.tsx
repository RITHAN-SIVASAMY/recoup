"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export function CommandPalette({
  open,
  onClose,
  sections,
  onNavigate,
}: {
  open: boolean;
  onClose: () => void;
  sections: { id: string; label: string; description: string }[];
  onNavigate: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (open) {
      setQuery("");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (open) window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const trimmed = query.trim();
  const looksLikeCaseId = trimmed.length >= 4 && !trimmed.includes(" ");
  const matchingSections = sections.filter((s) =>
    trimmed ? s.label.toLowerCase().includes(trimmed.toLowerCase()) : true,
  );

  function goToCase() {
    if (!looksLikeCaseId) return;
    router.push(`/dashboard/cases/${trimmed}`);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_24px_60px_rgba(13,15,26,0.25)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-[var(--color-border)] px-4 py-3">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--color-muted)]">
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && looksLikeCaseId && goToCase()}
            placeholder="Jump to a section, or paste a case ID…"
            className="w-full bg-transparent text-sm text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)]"
          />
          <kbd className="rounded border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-muted)]">
            esc
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2">
          {looksLikeCaseId && (
            <button
              onClick={goToCase}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-black/[0.03]"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-accent-soft)] font-mono text-[10px] font-semibold text-[var(--color-accent)]">
                ID
              </span>
              <span className="flex-1">
                <span className="text-[var(--color-ink)]">Open case</span>{" "}
                <span className="font-mono text-xs text-[var(--color-muted)]">{trimmed}</span>
              </span>
              <span className="text-xs text-[var(--color-muted)]">↵</span>
            </button>
          )}

          {matchingSections.length > 0 && (
            <div className="mt-1">
              <div className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
                Sections
              </div>
              {matchingSections.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onNavigate(s.id)}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-black/[0.03]"
                >
                  <span className="flex-1">
                    <span className="text-[var(--color-ink)]">{s.label}</span>
                    <span className="ml-2 text-xs text-[var(--color-muted)]">{s.description}</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {!looksLikeCaseId && matchingSections.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-[var(--color-muted)]">No matches.</div>
          )}
        </div>
      </div>
    </div>
  );
}
