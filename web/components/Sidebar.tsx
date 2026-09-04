"use client";

import type { ReactNode } from "react";

export type NavItem = {
  id: string;
  label: string;
  icon: ReactNode;
  badge?: number;
};

const ICON_PROPS = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export const NAV_ICONS = {
  overview: (
    <svg {...ICON_PROPS}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  governance: (
    <svg {...ICON_PROPS}>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
      <path d="M9.5 12l2 2 3.5-4" />
    </svg>
  ),
  insights: (
    <svg {...ICON_PROPS}>
      <path d="M3 21h18" />
      <rect x="6" y="11" width="3.5" height="7" rx="0.5" />
      <rect x="12" y="6" width="3.5" height="12" rx="0.5" />
      <rect x="18" y="14" width="3.5" height="4" rx="0.5" />
    </svg>
  ),
  simulate: (
    <svg {...ICON_PROPS}>
      <path d="M9 3h6" />
      <path d="M10 3v6l-5.5 9.2A1.5 1.5 0 0 0 5.8 21h12.4a1.5 1.5 0 0 0 1.3-2.8L14 9V3" />
      <path d="M7.5 15h9" />
    </svg>
  ),
};

export function Sidebar({
  navItems,
  activeId,
  onSelect,
  footer,
}: {
  navItems: NavItem[];
  activeId: string;
  onSelect: (id: string) => void;
  footer: ReactNode;
}) {
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-[var(--color-rail-border)] bg-[var(--color-rail-bg)]">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--color-rail-accent)] to-[var(--color-accent-2)] font-display text-sm font-bold text-white">
          R
        </div>
        <div>
          <div className="font-display text-[15px] font-semibold leading-none text-white">Recoup</div>
          <div className="mt-1 text-[10px] font-medium uppercase tracking-wider text-[var(--color-rail-muted)]">
            Recovery console
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {navItems.map((item) => {
          const active = item.id === activeId;
          return (
            <button
              key={item.id}
              onClick={() => onSelect(item.id)}
              className={`group relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "bg-[var(--color-rail-active)] text-[var(--color-rail-text-active)]"
                  : "text-[var(--color-rail-text)] hover:bg-white/[0.04] hover:text-white"
              }`}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-full bg-[var(--color-rail-accent)]" />
              )}
              <span className={active ? "text-[var(--color-rail-accent)]" : "text-[var(--color-rail-muted)] group-hover:text-[var(--color-rail-text)]"}>
                {item.icon}
              </span>
              <span className="flex-1 text-left">{item.label}</span>
              {typeof item.badge === "number" && item.badge > 0 && (
                <span
                  className={`inline-flex min-w-[20px] items-center justify-center rounded-full px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                    active ? "bg-[var(--color-rail-accent)] text-white" : "bg-white/[0.08] text-[var(--color-rail-text)]"
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-[var(--color-rail-border)] px-3 py-4">{footer}</div>
    </aside>
  );
}
