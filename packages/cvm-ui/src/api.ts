// Thin fetch client. In dev, Vite proxies /api to FastAPI on :8000 (prefix stripped).
// In prod, Caddy does the same for the cvm-api container.
const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  }
  const res = await fetch(url.toString(), { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

// ---------- Types ----------

export type Sector = string;

export interface CompanyRow {
  cd_cvm: number;
  name: string;
  sector: Sector | null;
  tickers: string[];
}

export interface CompanyDetail {
  cd_cvm: number;
  name: string;
  cnpj: string | null;
  sector: Sector | null;
  situation: string | null;
  tickers: { ticker: string; kind: string | null }[];
}

export interface ScreenRow {
  ticker: string;
  kind: string | null;
  cd_cvm: number;
  name: string;
  sector: Sector | null;
  period: string;
  revenue?: number | null;
  ebit?: number | null;
  ebitda?: number | null;
  net_income?: number | null;
  equity?: number | null;
  net_debt?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  ebitda_margin?: number | null;
  roe?: number | null;
  roa?: number | null;
  roic?: number | null;
  debt_to_equity?: number | null;
  current_ratio?: number | null;
  [extra: string]: unknown;
}

export interface VersionInfo {
  version: string;
  last_sync: string | null;
}

export interface StatementRow {
  period: string;
  account_code: string;
  account_desc: string;
  value: number | null;
}

export interface IndicatorsResp {
  cd_cvm: number;
  scope: string;
  freq: string;
  periods: Record<string, Record<string, number | null>>;
  growth: Record<string, Record<string, { qoq: number | null; yoy: number | null }>>;
}

// ---------- Endpoints ----------

export const api = {
  version: () => get<VersionInfo>("/version"),

  companies: (q?: string, limit = 50, offset = 0) =>
    get<CompanyRow[]>("/companies", {
      ...(q ? { q } : {}),
      limit,
      offset,
    }),

  company: (cd_cvm: number) => get<CompanyDetail>(`/companies/${cd_cvm}`),

  screen: (
    opts: { scope?: "con" | "ind"; freq?: "annual" | "quarterly"; limit?: number } = {},
  ) =>
    get<ScreenRow[]>("/screen", {
      scope: opts.scope ?? "con",
      freq: opts.freq ?? "annual",
      limit: opts.limit ?? 500,
    }),

  statements: (
    cd_cvm: number,
    opts: {
      statement?: "DRE" | "BPA" | "BPP" | "DFC_MD" | "DFC_MI" | "DMPL" | "DVA";
      scope?: "con" | "ind";
      freq?: "annual" | "quarterly";
    } = {},
  ) =>
    get<StatementRow[]>(`/companies/${cd_cvm}/statements`, {
      statement: opts.statement ?? "DRE",
      scope: opts.scope ?? "con",
      freq: opts.freq ?? "annual",
    }),

  companyIndicators: (
    cd_cvm: number,
    opts: { scope?: "con" | "ind"; freq?: "annual" | "quarterly" } = {},
  ) =>
    get<IndicatorsResp>(`/companies/${cd_cvm}/indicators`, {
      scope: opts.scope ?? "con",
      freq: opts.freq ?? "annual",
    }),
};

// ---------- Formatting helpers ----------

export const fmtPct = (v: number | null | undefined, digits = 1): string =>
  v == null ? "—" : (v * 100).toFixed(digits) + "%";

export const fmtBRL = (v: number | null | undefined, digits = 0): string => {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(digits) + "B";
  if (abs >= 1e6) return (v / 1e6).toFixed(digits) + "M";
  if (abs >= 1e3) return (v / 1e3).toFixed(digits) + "K";
  return v.toFixed(digits);
};

export const fmtNum = (v: number | null | undefined, digits = 2): string =>
  v == null ? "—" : v.toFixed(digits);
