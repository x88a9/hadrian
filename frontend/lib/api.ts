// Typed fetch-based API client.
// Base URL from NEXT_PUBLIC_API_URL (defaults to localhost).
// Data changes on import, hence cache: "no-store".

import type {
  AccountBalanceEntry,
  AccountBalanceResponse,
  AssetSetting,
  AssetSettingCreatePayload,
  AutoAssignResponse,
  Concept,
  ConceptGraph,
  ConceptsResponse,
  ImportRunResponse,
  LiveMetrics,
  LiveTrade,
  LiveTradeCreatePayload,
  LiveTradeListResponse,
  LiveTradesQuery,
  LiveTradeUpdatePayload,
  MonteCarloQuery,
  MonteCarloResponse,
  RiskCalcRequest,
  RiskCalcResponse,
  SystemConceptsResponse,
  SystemCreatePayload,
  SystemDetail,
  SystemsResponse,
  SystemUpdatePayload,
  TopographyResponse,
  Trade,
  TradeCreatePayload,
  TradeListResponse,
  TradeUpdatePayload,
  TransitionPayload,
  Venue,
  VenuesResponse,
  WalkForwardQuery,
  WalkForwardResponse,
} from "./types";

// NEXT_PUBLIC_API_URL wins. Without it the browser uses the hostname the page
// was loaded from, so localhost and a LAN IP both work without a rebuild.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://127.0.0.1:8000");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch (err) {
    // Network/connection error: the backend is unreachable.
    const message = err instanceof Error ? err.message : "Network error";
    throw new ApiError(0, message);
  }

  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") {
        message = body.detail;
      } else if (body && typeof body.message === "string") {
        message = body.message;
      }
    } catch {
      // Body is not JSON -> keep the default message.
    }
    throw new ApiError(res.status, message);
  }

  // 204 No Content (e.g. DELETE) or an empty body -> do not parse JSON.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  const text = await res.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export interface TradesQuery {
  system_id?: number;
  direction?: "long" | "short";
  win_loss?: "win" | "loss" | "draw";
  source?: "manual" | "auto" | "ui";
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
  order?: "asc" | "desc";
}

function buildQuery(params: Record<string, unknown> | object): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    sp.set(key, String(value));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

export function getSystems(): Promise<SystemsResponse> {
  return request<SystemsResponse>("/systems");
}

export function getSystem(id: number): Promise<SystemDetail> {
  return request<SystemDetail>(`/systems/${id}`);
}

// --- Phase 6: System-Write (POST/PATCH/DELETE) ---

// POST /systems is a silent upsert by name, so the UI has to block existing
// names before calling it (see SystemFormDialog).
export function createSystem(
  payload: SystemCreatePayload,
): Promise<SystemDetail> {
  return request<SystemDetail>("/systems", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// PATCH /systems/{id}: send only explicitly set fields (exclude_unset).
export function updateSystem(
  id: number,
  payload: SystemUpdatePayload,
): Promise<SystemDetail> {
  return request<SystemDetail>(`/systems/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSystem(id: number): Promise<void> {
  return request<void>(`/systems/${id}`, { method: "DELETE" });
}

export function getSystemConcepts(
  id: number,
): Promise<SystemConceptsResponse> {
  return request<SystemConceptsResponse>(`/systems/${id}/concepts`);
}

export function getTrades(
  params: TradesQuery = {},
): Promise<TradeListResponse> {
  return request<TradeListResponse>(`/trades${buildQuery(params)}`);
}

// --- Phase 6: Trade-Write (POST/PATCH/DELETE) ---

export function createTrade(payload: TradeCreatePayload): Promise<Trade> {
  return request<Trade>("/trades", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTrade(
  id: number,
  payload: TradeUpdatePayload,
): Promise<Trade> {
  return request<Trade>(`/trades/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteTrade(id: number): Promise<void> {
  return request<void>(`/trades/${id}`, { method: "DELETE" });
}

export function importXlsx(path?: string): Promise<ImportRunResponse> {
  return request<ImportRunResponse>("/import/xlsx", {
    method: "POST",
    body: JSON.stringify(path ? { path } : {}),
  });
}

// --- Phase 5: Programmatischer Import & Quant-Analytik ---

export function importProgrammatic(): Promise<ImportRunResponse> {
  return request<ImportRunResponse>("/import/programmatic", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getTopography(id: number): Promise<TopographyResponse> {
  return request<TopographyResponse>(`/systems/${id}/topography`);
}

export function getWalkForward(
  id: number,
  params: WalkForwardQuery = {},
): Promise<WalkForwardResponse> {
  return request<WalkForwardResponse>(
    `/systems/${id}/walkforward${buildQuery(params)}`,
  );
}

export function getMonteCarlo(
  id: number,
  params: MonteCarloQuery = {},
): Promise<MonteCarloResponse> {
  return request<MonteCarloResponse>(
    `/systems/${id}/montecarlo${buildQuery(params)}`,
  );
}

// --- Phase 4: Konzepte & Konzept-Graph ---

export function getConcepts(): Promise<ConceptsResponse> {
  return request<ConceptsResponse>("/concepts");
}

export function getConceptGraph(
  includeUnlinked = false,
): Promise<ConceptGraph> {
  return request<ConceptGraph>(
    `/concepts/graph${buildQuery({
      include_unlinked_systems: includeUnlinked,
    })}`,
  );
}

// POST /concepts: create a concept by name (upsert; 201 new, 200 existing).
export function createConcept(
  name: string,
  description?: string | null,
): Promise<Concept> {
  return request<Concept>("/concepts", {
    method: "POST",
    body: JSON.stringify({ name, description: description ?? null }),
  });
}

// source defaults to 'manual'. When the user confirms a suggestion from the
// auto-assign preview, source='heuristic' and match_reason are sent along so
// the edge keeps its heuristic provenance.
export function assignConcept(
  systemId: number,
  conceptId: number,
  opts?: { source?: "manual" | "heuristic"; matchReason?: string | null },
): Promise<void> {
  const body: Record<string, unknown> = { concept_id: conceptId };
  if (opts?.source) body.source = opts.source;
  if (opts?.matchReason != null) body.match_reason = opts.matchReason;
  return request<void>(`/systems/${systemId}/concepts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function unassignConcept(
  systemId: number,
  conceptId: number,
): Promise<void> {
  return request<void>(`/systems/${systemId}/concepts/${conceptId}`, {
    method: "DELETE",
  });
}

// dryRun=true computes the suggestions without persisting anything.
export function autoAssignConcepts(
  dryRun = false,
): Promise<AutoAssignResponse> {
  return request<AutoAssignResponse>(
    `/concepts/auto-assign${buildQuery({ dry_run: dryRun })}`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

// --- Live trading: risk calculator, trades, venues, account balance ---

export function calcRisk(payload: RiskCalcRequest): Promise<RiskCalcResponse> {
  return request<RiskCalcResponse>("/risk/calc", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getLiveTrades(
  params: LiveTradesQuery = {},
): Promise<LiveTradeListResponse> {
  return request<LiveTradeListResponse>(`/live-trades${buildQuery(params)}`);
}

export function getLiveMetrics(systemId?: number): Promise<LiveMetrics> {
  return request<LiveMetrics>(`/live-trades/metrics${buildQuery({ system_id: systemId })}`);
}

export function getLiveTrade(id: number): Promise<LiveTrade> {
  return request<LiveTrade>(`/live-trades/${id}`);
}

export function createLiveTrade(
  payload: LiveTradeCreatePayload,
): Promise<LiveTrade> {
  return request<LiveTrade>("/live-trades", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateLiveTrade(
  id: number,
  payload: LiveTradeUpdatePayload,
): Promise<LiveTrade> {
  return request<LiveTrade>(`/live-trades/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function transitionLiveTrade(
  id: number,
  payload: TransitionPayload,
): Promise<LiveTrade> {
  return request<LiveTrade>(`/live-trades/${id}/transition`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteLiveTrade(id: number): Promise<void> {
  return request<void>(`/live-trades/${id}`, { method: "DELETE" });
}

export function getVenues(): Promise<VenuesResponse> {
  return request<VenuesResponse>("/venues");
}

export function createVenue(
  name: string,
  notes?: string | null,
): Promise<Venue> {
  return request<Venue>("/venues", {
    method: "POST",
    body: JSON.stringify({ name, notes: notes ?? null }),
  });
}

export function updateVenue(
  id: number,
  name: string,
  notes?: string | null,
): Promise<Venue> {
  return request<Venue>(`/venues/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name, notes: notes ?? null }),
  });
}

export function getAssetSettings(
  venueId?: number,
  asset?: string,
  current = false,
): Promise<AssetSetting[]> {
  return request<AssetSetting[]>(
    `/asset-settings${buildQuery({ venue_id: venueId, asset, current })}`,
  );
}

// Creates a NEW settings version; existing trades are never altered.
export function createAssetSetting(
  venueId: number,
  payload: AssetSettingCreatePayload,
): Promise<AssetSetting> {
  return request<AssetSetting>(`/venues/${venueId}/asset-settings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getBalance(): Promise<AccountBalanceResponse> {
  return request<AccountBalanceResponse>("/account/balance");
}

// Absolute correction of the account balance (append-only).
export function correctBalance(
  balance: number,
  note?: string | null,
): Promise<AccountBalanceEntry> {
  return request<AccountBalanceEntry>("/account/balance", {
    method: "POST",
    body: JSON.stringify({ balance, note: note ?? null }),
  });
}
