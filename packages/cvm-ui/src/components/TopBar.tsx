import { createMemo, createSignal, onCleanup, type Component } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import { api } from "../api";

const formatUTC = (d: Date) => d.toISOString().slice(11, 19) + " UTC";

export const TopBar: Component = () => {
  const [now, setNow] = createSignal(new Date());
  const tick = setInterval(() => setNow(new Date()), 1000);
  onCleanup(() => clearInterval(tick));

  const version = createQuery(() => ({
    queryKey: ["version"],
    queryFn: api.version,
    staleTime: 60_000,
  }));

  const screen = createQuery(() => ({
    queryKey: ["screen", "annual", "con"],
    queryFn: () => api.screen({ freq: "annual", scope: "con" }),
    staleTime: 300_000,
  }));

  const stats = createMemo(() => {
    const rows = screen.data ?? [];
    const companies = new Set<number>();
    const sectors = new Set<string>();
    let withRoe = 0;
    for (const r of rows) {
      companies.add(r.cd_cvm);
      if (r.sector) sectors.add(r.sector);
      if (r.roe != null) withRoe++;
    }
    return {
      tickers: rows.length,
      companies: companies.size,
      sectors: sectors.size,
      coverage: rows.length > 0 ? withRoe / rows.length : 0,
    };
  });

  return (
    <header class="relative z-20 flex h-10 shrink-0 items-center justify-between border-b border-border bg-bg-elev px-4">
      <div class="flex items-center gap-6 font-mono text-[11px] text-text-dim">
        <Stat label="TICKERS" value={stats().tickers.toString()} />
        <Stat label="COMPANIES" value={stats().companies.toString()} />
        <Stat label="SECTORS" value={stats().sectors.toString()} />
        <Stat label="COVERAGE" value={(stats().coverage * 100).toFixed(0) + "%"} />
      </div>
      <div class="flex items-center gap-5 font-mono text-[11px]">
        <Stat label="SYNC" value={version.data?.last_sync?.slice(0, 10) ?? "—"} />
        <Stat label="VER" value={version.data?.version ?? "—"} />
        <div class="tabular text-text-faint">{formatUTC(now())}</div>
      </div>
    </header>
  );
};

const Stat: Component<{ label: string; value: string }> = (p) => (
  <div class="flex items-center gap-2">
    <span class="tracking-[0.14em] text-text-faint">{p.label}</span>
    <span class="tabular text-text">{p.value}</span>
  </div>
);
