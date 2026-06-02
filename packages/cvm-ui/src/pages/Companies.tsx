import {
  For,
  Show,
  createMemo,
  createSignal,
  type Component,
} from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import { createQuery } from "@tanstack/solid-query";
import {
  api,
  fmtBRL,
  fmtPct,
  fmtNum,
  type CompanyRow,
  type StatementRow,
} from "../api";

type Freq = "annual" | "quarterly";
type Scope = "con" | "ind";

export const Companies: Component = () => {
  const params = useParams<{ cd_cvm?: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = createSignal("");

  const list = createQuery(() => ({
    queryKey: ["companies", search()],
    queryFn: () => api.companies(search() || undefined, 200, 0),
  }));

  const selected = () => (params.cd_cvm ? Number(params.cd_cvm) : null);

  return (
    <div class="flex h-full font-mono text-[12px]">
      <aside class="flex w-[260px] shrink-0 flex-col border-r border-border bg-bg-elev/60">
        <div class="shrink-0 border-b border-border p-3">
          <div class="mb-2 text-[10px] uppercase tracking-[0.14em] text-text-faint">
            companies
          </div>
          <input
            type="search"
            placeholder="filter…"
            value={search()}
            onInput={(e) => setSearch(e.currentTarget.value)}
            class="w-full rounded border border-border bg-bg px-2 py-1 text-[12px] text-text outline-none focus:border-amber-dim"
          />
        </div>
        <div class="flex-1 overflow-auto">
          <Show
            when={!list.isPending}
            fallback={<div class="p-3 text-text-faint">loading…</div>}
          >
            <For each={list.data ?? []}>
              {(c) => (
                <CompanyListItem
                  row={c}
                  active={selected() === c.cd_cvm}
                  onClick={() => navigate(`/companies/${c.cd_cvm}`)}
                />
              )}
            </For>
          </Show>
        </div>
      </aside>

      <div class="min-w-0 flex-1 overflow-auto">
        <Show
          when={selected() != null}
          fallback={
            <div class="p-6 text-text-faint">
              select a company on the left
            </div>
          }
        >
          <CompanyDetailView cd_cvm={selected()!} />
        </Show>
      </div>
    </div>
  );
};

const CompanyListItem: Component<{
  row: CompanyRow;
  active: boolean;
  onClick: () => void;
}> = (p) => (
  <button
    type="button"
    onClick={p.onClick}
    class="block w-full border-b border-border px-3 py-2 text-left hover:bg-bg-elev"
    classList={{ "bg-bg-elev-2": p.active }}
  >
    <div class="flex items-center justify-between gap-2">
      <span
        class="truncate text-[12px]"
        classList={{
          "text-amber": p.active,
          "text-text": !p.active,
        }}
      >
        {p.row.name}
      </span>
      <span class="shrink-0 tabular text-[10px] text-text-faint">
        {p.row.tickers[0] ?? p.row.cd_cvm}
      </span>
    </div>
    <Show when={p.row.sector}>
      <div class="mt-0.5 truncate text-[10px] text-text-faint">
        {p.row.sector}
      </div>
    </Show>
  </button>
);

const CompanyDetailView: Component<{ cd_cvm: number }> = (props) => {
  const [freq, setFreq] = createSignal<Freq>("annual");
  const [scope, setScope] = createSignal<Scope>("con");

  const detail = createQuery(() => ({
    queryKey: ["company", props.cd_cvm],
    queryFn: () => api.company(props.cd_cvm),
  }));

  const dre = createQuery(() => ({
    queryKey: ["statements", props.cd_cvm, "DRE", scope(), freq()],
    queryFn: () =>
      api.statements(props.cd_cvm, { statement: "DRE", scope: scope(), freq: freq() }),
  }));
  const bpa = createQuery(() => ({
    queryKey: ["statements", props.cd_cvm, "BPA", scope(), freq()],
    queryFn: () =>
      api.statements(props.cd_cvm, { statement: "BPA", scope: scope(), freq: freq() }),
  }));
  const bpp = createQuery(() => ({
    queryKey: ["statements", props.cd_cvm, "BPP", scope(), freq()],
    queryFn: () =>
      api.statements(props.cd_cvm, { statement: "BPP", scope: scope(), freq: freq() }),
  }));
  const indicators = createQuery(() => ({
    queryKey: ["indicators", props.cd_cvm, scope(), freq()],
    queryFn: () => api.companyIndicators(props.cd_cvm, { scope: scope(), freq: freq() }),
  }));

  const balance = createMemo<StatementRow[]>(() => [
    ...(bpa.data ?? []),
    ...(bpp.data ?? []),
  ]);

  return (
    <div class="flex flex-col">
      <header class="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-4 border-b border-border bg-bg px-5 py-3">
        <div class="min-w-0">
          <Show when={detail.data} fallback={<div class="text-text-faint">loading…</div>}>
            {(d) => (
              <>
                <div class="flex items-baseline gap-3">
                  <h1 class="truncate text-amber text-[15px] tracking-wider">
                    {d().name}
                  </h1>
                  <span class="tabular text-[11px] text-text-faint">
                    cd_cvm {d().cd_cvm}
                  </span>
                </div>
                <div class="mt-1 flex items-center gap-4 text-[11px] text-text-faint">
                  <Show when={d().sector}>
                    <span>{d().sector}</span>
                  </Show>
                  <Show when={d().tickers.length > 0}>
                    <span class="tabular text-text-dim">
                      {d().tickers.map((t) => t.ticker).join(" · ")}
                    </span>
                  </Show>
                </div>
              </>
            )}
          </Show>
        </div>
        <div class="flex items-center gap-3">
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

      <div class="grid grid-cols-2 gap-px bg-border">
        <StatementBlock
          title="Income (DRE)"
          rows={dre.data ?? []}
          loading={dre.isPending}
          freq={freq()}
        />
        <StatementBlock
          title="Balance sheet (BPA + BPP)"
          rows={balance()}
          loading={bpa.isPending || bpp.isPending}
          freq={freq()}
        />
      </div>

      <IndicatorsPanel
        loading={indicators.isPending}
        data={indicators.data}
        freq={freq()}
      />
    </div>
  );
};

interface StatementBlockProps {
  title: string;
  rows: StatementRow[];
  loading: boolean;
  freq: Freq;
}

const StatementBlock: Component<StatementBlockProps> = (p) => {
  const grouped = createMemo(() => groupByYear(p.rows, p.freq));
  const [openYears, setOpenYears] = createSignal<Set<string>>(new Set());

  // Default-open the most recent year as soon as data arrives.
  const ensureLatestOpen = createMemo(() => {
    const years = grouped().years;
    if (years.length === 0) return;
    setOpenYears((prev) => {
      if (prev.size > 0) return prev;
      const next = new Set(prev);
      next.add(years[0]);
      return next;
    });
  });
  ensureLatestOpen;

  const toggleYear = (y: string) => {
    setOpenYears((prev) => {
      const next = new Set(prev);
      if (next.has(y)) next.delete(y);
      else next.add(y);
      return next;
    });
  };

  return (
    <section class="bg-bg">
      <header class="flex items-center justify-between border-b border-border px-4 py-2">
        <h2 class="text-[11px] uppercase tracking-[0.14em] text-text-dim">
          {p.title}
        </h2>
        <span class="tabular text-[10px] text-text-faint">
          {p.rows.length} rows
        </span>
      </header>

      <Show
        when={!p.loading}
        fallback={<div class="px-4 py-6 text-text-faint">loading…</div>}
      >
        <Show
          when={grouped().years.length > 0}
          fallback={<div class="px-4 py-6 text-text-faint">no data</div>}
        >
          <For each={grouped().years}>
            {(year) => {
              const isOpen = () => openYears().has(year);
              const periods = () => grouped().byYear[year];
              return (
                <div class="border-b border-border">
                  <button
                    type="button"
                    onClick={() => toggleYear(year)}
                    class="flex w-full items-center justify-between px-4 py-2 text-left hover:bg-bg-elev"
                  >
                    <span class="flex items-center gap-2">
                      <span class="tabular text-text-faint">
                        {isOpen() ? "▾" : "▸"}
                      </span>
                      <span class="text-amber">{year}</span>
                      <span class="text-text-faint">
                        · {periods().length} period{periods().length === 1 ? "" : "s"}
                      </span>
                    </span>
                  </button>
                  <Show when={isOpen()}>
                    <StatementTable periods={periods()} />
                  </Show>
                </div>
              );
            }}
          </For>
        </Show>
      </Show>
    </section>
  );
};

interface PeriodGroup {
  period: string;
  rows: StatementRow[];
}

const StatementTable: Component<{ periods: PeriodGroup[] }> = (p) => {
  const merged = createMemo(() => {
    const accountOrder: string[] = [];
    const seen = new Set<string>();
    const descByCode = new Map<string, string>();
    const valuesByCode = new Map<string, Map<string, number | null>>();

    for (const g of p.periods) {
      for (const r of g.rows) {
        if (!seen.has(r.account_code)) {
          seen.add(r.account_code);
          accountOrder.push(r.account_code);
          descByCode.set(r.account_code, r.account_desc);
        }
        let bucket = valuesByCode.get(r.account_code);
        if (!bucket) {
          bucket = new Map();
          valuesByCode.set(r.account_code, bucket);
        }
        bucket.set(g.period, r.value);
      }
    }

    accountOrder.sort();

    return {
      periods: p.periods.map((g) => g.period),
      accounts: accountOrder.map((code) => ({
        code,
        desc: descByCode.get(code) ?? code,
        values: valuesByCode.get(code) ?? new Map<string, number | null>(),
      })),
    };
  });

  return (
    <div class="overflow-auto">
      <table class="w-full border-collapse">
        <thead class="bg-bg-elev text-[10px] uppercase tracking-wider text-text-faint">
          <tr class="border-b border-border">
            <th class="px-3 py-1.5 text-left font-normal">account</th>
            <For each={merged().periods}>
              {(period) => (
                <th class="px-3 py-1.5 text-right font-normal tabular">{period}</th>
              )}
            </For>
          </tr>
        </thead>
        <tbody>
          <For each={merged().accounts}>
            {(acc) => {
              const depth = acc.code.split(".").length - 1;
              const isHeader = depth <= 1;
              return (
                <tr
                  class="border-b border-border/60 hover:bg-bg-elev"
                  classList={{ "bg-bg-elev/40": isHeader }}
                >
                  <td
                    class="px-3 py-1 text-text-dim"
                    style={{ "padding-left": `${0.75 + depth * 0.9}rem` }}
                  >
                    <span class="tabular text-text-faint">{acc.code}</span>{" "}
                    <span classList={{ "text-text": isHeader }}>
                      {acc.desc}
                    </span>
                  </td>
                  <For each={merged().periods}>
                    {(period) => (
                      <td class="px-3 py-1 text-right tabular text-text">
                        {fmtBRL(acc.values.get(period) ?? null, 1)}
                      </td>
                    )}
                  </For>
                </tr>
              );
            }}
          </For>
        </tbody>
      </table>
    </div>
  );
};

interface IndicatorsPanelProps {
  loading: boolean;
  data:
    | {
        periods: Record<string, Record<string, number | null>>;
      }
    | undefined;
  freq: Freq;
}

const PCT_INDICATORS = new Set([
  "gross_margin",
  "operating_margin",
  "net_margin",
  "ebitda_margin",
  "roe",
  "roa",
  "roic",
]);

const IndicatorsPanel: Component<IndicatorsPanelProps> = (p) => {
  const sortedPeriods = createMemo(() => {
    if (!p.data) return [] as string[];
    return Object.keys(p.data.periods).sort().reverse();
  });

  const indicatorNames = createMemo(() => {
    if (!p.data) return [] as string[];
    const names = new Set<string>();
    for (const periodMap of Object.values(p.data.periods)) {
      for (const k of Object.keys(periodMap)) names.add(k);
    }
    return [...names].sort();
  });

  const groupedByYear = createMemo(() => {
    const byYear: Record<string, string[]> = {};
    for (const period of sortedPeriods()) {
      const year = period.slice(0, 4);
      (byYear[year] ??= []).push(period);
    }
    return Object.keys(byYear)
      .sort()
      .reverse()
      .map((year) => ({ year, periods: byYear[year] }));
  });

  const [openYears, setOpenYears] = createSignal<Set<string>>(new Set());
  const ensureLatestOpen = createMemo(() => {
    const years = groupedByYear();
    if (years.length === 0) return;
    setOpenYears((prev) => {
      if (prev.size > 0) return prev;
      const next = new Set(prev);
      next.add(years[0].year);
      return next;
    });
  });
  ensureLatestOpen;

  const toggleYear = (y: string) =>
    setOpenYears((prev) => {
      const next = new Set(prev);
      if (next.has(y)) next.delete(y);
      else next.add(y);
      return next;
    });

  const fmt = (name: string, v: number | null | undefined): string => {
    if (v == null) return "—";
    if (PCT_INDICATORS.has(name)) return fmtPct(v, 1);
    if (Math.abs(v) >= 1000) return fmtBRL(v, 1);
    return fmtNum(v, 2);
  };

  return (
    <section class="border-t border-border bg-bg">
      <header class="flex items-center justify-between border-b border-border px-4 py-2">
        <h2 class="text-[11px] uppercase tracking-[0.14em] text-text-dim">
          Indicators
        </h2>
        <span class="tabular text-[10px] text-text-faint">
          {indicatorNames().length} metrics · {sortedPeriods().length} periods
        </span>
      </header>
      <Show
        when={!p.loading}
        fallback={<div class="px-4 py-6 text-text-faint">loading…</div>}
      >
        <Show
          when={groupedByYear().length > 0}
          fallback={<div class="px-4 py-6 text-text-faint">no data</div>}
        >
          <For each={groupedByYear()}>
            {(yg) => {
              const isOpen = () => openYears().has(yg.year);
              return (
                <div class="border-b border-border">
                  <button
                    type="button"
                    onClick={() => toggleYear(yg.year)}
                    class="flex w-full items-center justify-between px-4 py-2 text-left hover:bg-bg-elev"
                  >
                    <span class="flex items-center gap-2">
                      <span class="tabular text-text-faint">
                        {isOpen() ? "▾" : "▸"}
                      </span>
                      <span class="text-amber">{yg.year}</span>
                      <span class="text-text-faint">
                        · {yg.periods.length} period
                        {yg.periods.length === 1 ? "" : "s"}
                      </span>
                    </span>
                  </button>
                  <Show when={isOpen()}>
                    <div class="overflow-auto">
                      <table class="w-full border-collapse">
                        <thead class="bg-bg-elev text-[10px] uppercase tracking-wider text-text-faint">
                          <tr class="border-b border-border">
                            <th class="px-3 py-1.5 text-left font-normal">
                              indicator
                            </th>
                            <For each={yg.periods}>
                              {(period) => (
                                <th class="px-3 py-1.5 text-right font-normal tabular">
                                  {period}
                                </th>
                              )}
                            </For>
                          </tr>
                        </thead>
                        <tbody>
                          <For each={indicatorNames()}>
                            {(name) => (
                              <tr class="border-b border-border/60 hover:bg-bg-elev">
                                <td class="px-3 py-1 text-text-dim">{name}</td>
                                <For each={yg.periods}>
                                  {(period) => (
                                    <td class="px-3 py-1 text-right tabular text-text">
                                      {fmt(name, p.data?.periods[period]?.[name])}
                                    </td>
                                  )}
                                </For>
                              </tr>
                            )}
                          </For>
                        </tbody>
                      </table>
                    </div>
                  </Show>
                </div>
              );
            }}
          </For>
        </Show>
      </Show>
    </section>
  );
};

const groupByYear = (
  rows: StatementRow[],
  _freq: Freq,
): { years: string[]; byYear: Record<string, PeriodGroup[]> } => {
  const byPeriod = new Map<string, StatementRow[]>();
  for (const r of rows) {
    let bucket = byPeriod.get(r.period);
    if (!bucket) {
      bucket = [];
      byPeriod.set(r.period, bucket);
    }
    bucket.push(r);
  }

  const byYear: Record<string, PeriodGroup[]> = {};
  for (const [period, bucket] of byPeriod) {
    const year = period.slice(0, 4);
    (byYear[year] ??= []).push({ period, rows: bucket });
  }
  for (const year of Object.keys(byYear)) {
    byYear[year].sort((a, b) => (a.period < b.period ? 1 : -1));
  }
  const years = Object.keys(byYear).sort().reverse();
  return { years, byYear };
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
