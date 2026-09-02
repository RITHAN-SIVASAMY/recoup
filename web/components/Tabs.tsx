"use client";

import { useState, type ReactNode } from "react";

export type TabDef = {
  id: string;
  label: string;
  badge?: number;
  content: ReactNode;
};

export function Tabs({ tabs, defaultTab }: { tabs: TabDef[]; defaultTab?: string }) {
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id);
  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div>
      <div className="sticky top-[57px] z-10 -mx-6 mb-6 border-b border-[var(--color-border)] bg-[var(--color-bg)]/90 px-6 backdrop-blur-sm">
        <nav className="flex gap-1 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTab?.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActive(tab.id)}
                className={`relative flex items-center gap-1.5 whitespace-nowrap px-3.5 py-3 text-sm font-medium transition ${
                  isActive
                    ? "text-[var(--color-accent)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-ink-soft)]"
                }`}
              >
                {tab.label}
                {typeof tab.badge === "number" && tab.badge > 0 && (
                  <span
                    className={`inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                      isActive
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-black/[0.06] text-[var(--color-muted)]"
                    }`}
                  >
                    {tab.badge}
                  </span>
                )}
                {isActive && (
                  <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-[var(--color-accent)]" />
                )}
              </button>
            );
          })}
        </nav>
      </div>
      <div className="space-y-6">{activeTab?.content}</div>
    </div>
  );
}
