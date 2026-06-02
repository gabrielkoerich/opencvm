import { For, Show, createMemo, createSignal, type Component } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import { api, fmtBRL, fmtPct, fmtNum, type ScreenRow } from "../api";

type Freq = "annual" | "quarterly";
type Scope = "con" | "ind";
type SortDir = "asc" | "desc";

interface Column {
  key: keyof ScreenRow;
  label: string;
  format: (v: unknown) => string;
  numeric: boolean;
}

const COLUMNS: Column[] = [
  { key: "revenue", label: "Revenue", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "ebit", label: "EBIT", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "ebitda", label: "EBITDA", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "net_income", label: "Net inc.", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "equity", label: "Equity", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "net_debt", label: "Net debt", format: (v) => fmtBRL(v as number | null), numeric: true },
  { key: "gross_margin", label: "GM", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "operating_margin", label: "OM", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "net_margin", label: "NM", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "roe", label: "ROE", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "roa", label: "ROA", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "roic", label: "ROIC", format: (v) => fmtPct(v as number | null), numeric: true },
  { key: "debt_to_equity", label: "D/E", format: (v) => fmtNum(v as number | null), numeric: true },
  { key: "current_ratio", label: "CR", format: (v) => fmtNum(v as number | null), numeric: true },
];

export const Screeners: Component = () => {
  const [freq, setFreq] = createSignal<Freq>("annual");
  const [scope, setScope] = createSignal<Scope>("con");
  const [query, setQuery] = createSignal("");
  const [sortKey, setSortKey] = createSignal<keyof ScreenRow>("revenue");
  const [sortDir, setSortDir] = createSignal<SortDir>("desc");

  const screen = createQuery(() => ({
    queryKey: ["screen", freq(), scope()],
    queryFn: () => api.screen({ freq: freq(), scope: scope() }),
  }));

  const filtered = createMemo(() => {
    const rows = screen.data ?? [];
    const q = query().trim().toUpperCase();
    const matched = q
      ? rows.filter(
          (r) =>
            r.ticker.includes(q) ||
            r.name.toUpperCase().includes(q) ||
            (r.sector ?? "").toUpperCase().includes(q),
        )
      : rows;
    const key = sortKey();
    const dir = sortDir() === "asc" ? 1 : -1;
    return [...matched].sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  });

  const toggleSort = (key: keyof ScreenRow) => {
    if (sortKey() === key) {
      setSortDir(sortDir() === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  return (
    <div class="flex h-full flex-col font-mono text-[12px]">
      <header class="flex shrink-0 items-center justify-between gap-4 border-b border-border px-4 py-3">
        <div class="flex items-center gap-4">
          <h1 class="text-amber tracking-wider">SCREENER</h1>
          <span class="text-[11px] text-text-faint">
            {filtered().length}/{screen.data?.length ?? 0} tickers
          </span>
        </div>

        <div class="flex items-center gap-3">
          <input
            type="search"
            placeholder="filter ticker / company / sector…"
            value={query()}
            onInput={(e) => setQuery(e.currentTarget.value)}
            class="w-72 rounded border border-border bg-bg-elev px-3 py-1 text-[12px] text-text outline-none focus:border-amber-dim"
          />
          <Segmented<Freq>
            value={freq()}
            options={[
              ["annual", "annual"],
              ["quarterly", "quarterly"],
            ]}
            onChange={setFreq}
          />
          <Segmented<Scope>
            value={scope()}
            options={[
              ["con", "consol."],
              ["ind", "indiv."],
            ]}
            onChange={setScope}
          />
        </div>
      </header>

      <div class="flex-1 overflow-auto">
        <Show
          when={!screen.isPending}
          fallback={<div class="p-6 text-text-faint">loading…</div>}
        >
          <Show
            when={!screen.isError}
            fallback={
              <div class="p-6 text-red">
                error: {(screen.error as Error | null)?.message ?? "unknown"}
              </div>
            }
          >
            <table class="w-full border-collapse">
              <thead class="sticky top-0 z-10 bg-bg-elev text-[11px] text-text-faint uppercase tracking-wider">
                <tr class="border-b border-border">
                  <Th
                    label="Ticker"
                    active={sortKey() === "ticker"}
                    dir={sortDir()}
                    onClick={() => toggleSort("ticker")}
                  />
                  <Th
                    label="Company"
                    active={sortKey() === "name"}
                    dir={sortDir()}
                    onClick={() => toggleSort("name")}
                  />
                  <Th
                    label="Sector"
                    active={sortKey() === "sector"}
                    dir={sortDir()}
                    onClick={() => toggleSort("sector")}
                  />
                  <Th
                    label="Period"
                    active={sortKey() === "period"}
                    dir={sortDir()}
                    onClick={() => toggleSort("period")}
                    align="right"
                  />
                  <For each={COLUMNS}>
                    {(col) => (
                      <Th
                        label={col.label}
                        active={sortKey() === col.key}
                        dir={sortDir()}
                        onClick={() => toggleSort(col.key)}
                        align="right"
                      />
                    )}
                  </For>
                </tr>
              </thead>
              <tbody>
                <For each={filtered()}>
                  {(row) => (
                    <tr class="border-b border-border hover:bg-bg-elev">
                      <td class="px-3 py-1.5 font-mono text-text">{row.ticker}</td>
                      <td class="max-w-[20rem] truncate px-3 py-1.5 text-text-dim">
                        {row.name}
                      </td>
                      <td class="max-w-[14rem] truncate px-3 py-1.5 text-text-faint">
                        {row.sector ?? "—"}
                      </td>
                      <td class="px-3 py-1.5 text-right text-text-faint tabular">
                        {row.period}
                      </td>
                      <For each={COLUMNS}>
                        {(col) => (
                          <td class="px-3 py-1.5 text-right tabular text-text">
                            {col.format(row[col.key])}
                          </td>
                        )}
                      </For>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </Show>
        </Show>
      </div>
    </div>
  );
};

const Segmented = <T extends string>(props: {
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) => (
  <div class="flex border border-border">
    <For each={props.options}>
      {([val, label]) => (
        <button
          type="button"
          onClick={() => props.onChange(val)}
          class="px-2 py-0.5 text-[11px] tracking-wider uppercase"
          classList={{
            "bg-bg-elev-2 text-text": props.value === val,
            "text-text-dim hover:text-text": props.value !== val,
          }}
        >
          {label}
        </button>
      )}
    </For>
  </div>
);

const Th: Component<{
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}> = (p) => (
  <th
    class="cursor-pointer select-none whitespace-nowrap px-3 py-2 font-normal hover:text-text"
    classList={{
      "text-right": p.align === "right",
      "text-left": p.align !== "right",
      "text-amber": p.active,
    }}
    onClick={p.onClick}
  >
    {p.label}
    <Show when={p.active}>
      <span class="ml-1">{p.dir === "asc" ? "↑" : "↓"}</span>
    </Show>
  </th>
);
