import { Show, type Component } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import { api } from "../api";

export const Sidebar: Component = () => {
  const loc = useLocation();
  const version = createQuery(() => ({
    queryKey: ["version"],
    queryFn: api.version,
    staleTime: 60_000,
  }));

  return (
    <aside class="relative z-10 flex h-full w-[240px] shrink-0 flex-col border-r border-border bg-bg-elev">
      <header class="flex h-10 shrink-0 items-center border-b border-border px-4">
        <A
          href="/"
          class="font-mono text-[15px] font-medium tracking-tight text-text hover:text-amber"
        >
          OPEN<span class="text-amber">CVM</span>
          <span class="text-amber">//</span>
        </A>
      </header>

      <nav class="flex flex-1 flex-col gap-6 overflow-auto px-3 py-4">
        <SectionLabel label="Browse" />
        <NavLink
          href="/screeners"
          active={loc.pathname === "/" || loc.pathname.startsWith("/screeners")}
          label="Screener"
        />
        <NavLink
          href="/companies"
          active={loc.pathname.startsWith("/companies")}
          label="Companies"
        />

        <SectionLabel label="Tools" />
        <NavLink
          href="/portfolios"
          active={loc.pathname.startsWith("/portfolios")}
          label="Portfolios"
          dim="soon"
        />
        <NavLink
          href="/compare"
          active={loc.pathname.startsWith("/compare")}
          label="Compare"
          dim="soon"
        />
      </nav>

      <footer class="border-t border-border px-4 py-3 font-mono text-[11px] text-text-dim">
        <div class="flex justify-between">
          <span>data</span>
          <span class="tabular text-text">
            {version.data?.last_sync?.slice(0, 10) ?? "—"}
          </span>
        </div>
        <div class="mt-1 flex justify-between">
          <span>version</span>
          <span class="tabular text-text-faint">
            {version.data?.version?.slice(0, 8) ?? "—"}
          </span>
        </div>
      </footer>
    </aside>
  );
};

const SectionLabel: Component<{ label: string }> = (p) => (
  <div class="px-3 pt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">
    ── {p.label} ──
  </div>
);

const NavLink: Component<{
  href: string;
  active: boolean;
  label: string;
  dim?: string;
}> = (p) => (
  <A
    href={p.href}
    class="flex items-center justify-between rounded px-3 py-1.5 text-[12px] hover:bg-bg-elev-2"
    classList={{
      "bg-bg-elev-2 text-text": p.active,
      "text-text-dim": !p.active,
    }}
  >
    <span>{p.label}</span>
    <Show when={p.dim}>
      <span class="font-mono text-[10px] text-text-faint">{p.dim}</span>
    </Show>
  </A>
);
