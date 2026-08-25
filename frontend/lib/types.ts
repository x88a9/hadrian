// TypeScript types mirroring the API contract one-to-one.
// Every numeric metric field is `| null`; null means not computable.
// Dates are ISO-8601 strings without a timezone.

export type Grade = "A+" | "A" | "B" | "C" | "D" | "F";

export type SystemStatus = "backtest" | "live_testing" | "active" | "retired";

export type ImportStatus = "complete" | "incomplete";

export type Direction = "long" | "short";

export type WinLoss = "win" | "loss" | "draw";

export type TradeSource = "manual" | "auto" | "ui";

// How a system was created: imported vs. created in the UI.
export type SystemOrigin = "import" | "ui";

export type TabStatus = "complete" | "incomplete" | "skipped";

// Where a system's data came from: hand-maintained (xlsx/CSV), an upstream
// research engine, or this platform's own backtesting engine.
export type Provenance = "manual" | "programmatic" | "engine";

export interface MetricsBlock {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  ev: number | null;
  total_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  ece: number | null;
  evol: number | null;
  composite_score: number | null;
  composite_grade: Grade | null;
  ev_grade: Grade | null;
  ece_grade: Grade | null;
  evol_grade: Grade | null;
  first_trade_at: string | null;
  last_trade_at: string | null;
  span_days: number | null;
  // Phase 3 (additiv): Risiko- & Verteilungskennzahlen. Backend liefert sie
  // may not yet be set -> always treat as optional/nullable.
  profit_factor?: number | null;
  max_drawdown_r?: number | null;
  romad?: number | null;
  skewness?: number | null;
  r_p05?: number | null;
  r_p25?: number | null;
  r_p50?: number | null;
  r_p75?: number | null;
  r_p95?: number | null;
}

export interface SystemMetrics {
  all: MetricsBlock;
  is: MetricsBlock;
  oos: MetricsBlock;
}

export interface SystemSummary {
  id: number;
  name: string;
  prefix: string;
  timeframe: string;
  // The asset the system was backtested on.
  asset: string | null;
  status: SystemStatus;
  import_status: ImportStatus;
  provenance: Provenance;
  source_engine: string | null;
  // Phase 6: 'import' | 'ui' (Anlage-Kanal, Re-Import-Schutz).
  origin: SystemOrigin;
  metrics: SystemMetrics;
}

export interface SystemsResponse {
  split_date: string;
  items: SystemSummary[];
}

export interface ReportedMetrics {
  win_rate: number | null;
  ev: number | null;
  total_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  total_trades: number | null;
  wins: number | null;
  losses: number | null;
  ece: number | null;
  evol: number | null;
  composite_grade: Grade | null;
  ev_grade: Grade | null;
  ece_grade: Grade | null;
  evol_grade: Grade | null;
}

export interface SystemDetail {
  id: number;
  name: string;
  prefix: string;
  timeframe: string;
  status: SystemStatus;
  import_status: ImportStatus;
  provenance: Provenance;
  source_engine: string | null;
  asset: string | null;
  entry_rule: string | null;
  sl_rule: string | null;
  tp_rule: string | null;
  notes: string | null;
  reported_metrics: ReportedMetrics | null;
  metrics: SystemMetrics;
  // Phase 6: 'import' | 'ui'.
  origin: SystemOrigin;
  // Field names overridden in the UI and protected against re-import.
  user_overrides: string[];
  // Split date for the OOS marker in the detail view.
  split_date?: string;
}

export interface Trade {
  id: number;
  system_id: number;
  system_name: string;
  trade_datetime: string | null;
  zone: string | null;
  timeframe: string | null;
  entry: number | null;
  sl: number | null;
  exit: number | null;
  direction: Direction | null;
  r_value: number | null;
  win_loss: WinLoss | null;
  source: TradeSource;
}

export interface TradeListResponse {
  total: number;
  limit: number;
  offset: number;
  items: Trade[];
}

export interface ImportTabResult {
  tab: string;
  system_name: string | null;
  status: TabStatus;
  trades: number;
  message: string | null;
}

export interface ImportRunResponse {
  id: number;
  started_at: string;
  finished_at: string | null;
  file_path: string;
  tabs_total: number;
  systems_complete: number;
  systems_incomplete: number;
  tabs_skipped: number;
  trades_imported: number;
  tab_results: ImportTabResult[];
}

// --- Phase 6: Write-Payloads (System-/Trade-CRUD) ---

// POST /systems — only `name` is required; everything else is optional (upsert).
export interface SystemCreatePayload {
  name: string;
  asset?: string | null;
  status?: SystemStatus;
  entry_rule?: string | null;
  sl_rule?: string | null;
  tp_rule?: string | null;
  notes?: string | null;
}

// PATCH /systems/{id} — send only changed fields (exclude_unset semantics:
// do NOT send unchanged fields, or they land in user_overrides needlessly).
export interface SystemUpdatePayload {
  status?: SystemStatus;
  asset?: string | null;
  entry_rule?: string | null;
  sl_rule?: string | null;
  tp_rule?: string | null;
  notes?: string | null;
  timeframe?: string | null;
}

// POST /trades — exactly one of system_id / system_name; source defaults to 'auto'.
export interface TradeCreatePayload {
  system_id?: number;
  system_name?: string;
  trade_datetime?: string | null;
  zone?: string | null;
  timeframe?: string | null;
  entry?: number | null;
  sl?: number | null;
  exit?: number | null;
  direction?: Direction | null;
  r_value?: number | null;
  win_loss?: WinLoss | null;
  source?: "auto" | "ui";
}

// PATCH /trades/{id} — system_id and source are immutable.
export interface TradeUpdatePayload {
  trade_datetime?: string | null;
  zone?: string | null;
  timeframe?: string | null;
  entry?: number | null;
  sl?: number | null;
  exit?: number | null;
  direction?: Direction | null;
  r_value?: number | null;
  win_loss?: WinLoss | null;
}

// GET /systems/{id}/concepts — a concept assignment with provenance and match reason.
export interface ConceptAssignment {
  concept_id: number;
  name: string;
  description: string | null;
  source: AssignmentSource;
  match_reason: string | null;
  created_at: string;
}

export interface SystemConceptsResponse {
  items: ConceptAssignment[];
}

// --- Phase 4: Konzepte & Konzept-Graph (additiv) ---

export type AssignmentSource = "manual" | "heuristic";

export interface Concept {
  id: number;
  name: string;
  description: string | null;
  system_count: number;
}

export interface ConceptsResponse {
  items: Concept[];
}

// Graph-Contract (D2): Knoten-IDs sind namespaced ("concept:1" | "system:7").
export type GraphNodeType = "concept" | "system";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  // Nur bei Systemknoten gesetzt.
  status?: SystemStatus;
  import_status?: ImportStatus;
}

export interface GraphLink {
  source: string;
  target: string;
  assignment_source: AssignmentSource;
}

export interface ConceptGraph {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface AutoAssignAssignment {
  system: string;
  concept: string;
  rule: string;
  // Match reason plus IDs for accepting a single suggestion,
  // status = 'created' (real) | 'proposed' (dry_run-Vorschau).
  reason?: string | null;
  system_id?: number | null;
  concept_id?: number | null;
  status?: string;
}

export interface AutoAssignResponse {
  created: number;
  skipped_existing: number;
  assignments: AutoAssignAssignment[];
}

// --- Phase 5: Quant-Analytik (Topographie / Walk-Forward / Monte-Carlo) ---

// Achsenwerte koennen numerisch (sl_buffer/tp_norm) oder kategorial (tp_type) sein.
export type AxisValue = number | string;

export interface TopographyCell {
  x: AxisValue;
  y: AxisValue;
  value: number | null;
  net_ev: number | null;
  n_trades: number | null;
  low_confidence: boolean;
  insufficient_sample: boolean;
  neighbor_min: number | null;
  neighbor_max: number | null;
  neighbor_mean: number | null;
  n_neighbors: number | null;
}

export interface TopographyBest {
  x: AxisValue;
  y: AxisValue;
  value: number | null;
}

// robust_best traegt zusaetzlich den Plateau-Floor (min(value, neighbor_min)).
export interface TopographyRobustBest extends TopographyBest {
  floor: number | null;
}

export interface TopographyGrid {
  id: number;
  label: string;
  param_x: string;
  param_y: string;
  metric: string;
  x_values: AxisValue[];
  y_values: AxisValue[];
  cells: TopographyCell[];
  pct_positive: number | null; // Anteil (0..1)
  best: TopographyBest | null;
  robust_best: TopographyRobustBest | null;
}

export interface TopographyResponse {
  system_id: number;
  pre_gate: boolean;
  grids: TopographyGrid[];
}

export interface WalkForwardWindow {
  index: number;
  is_start: string;
  is_end: string;
  oos_start: string;
  oos_end: string;
  n_is: number;
  n_oos: number;
  is_ev: number | null;
  oos_ev: number | null;
}

export interface WalkForwardResponse {
  system_id: number;
  is_months: number;
  oos_months: number;
  step_months: number;
  min_oos_trades: number;
  n_windows: number;
  n_windows_evaluated: number;
  pct_positive: number | null; // Prozent (0..100)
  oos_ev_mean: number | null;
  oos_ev_std: number | null;
  n_dated_trades: number;
  windows: WalkForwardWindow[];
}

export interface WalkForwardQuery {
  is_months?: number;
  oos_months?: number;
  step_months?: number;
  min_oos_trades?: number;
}

export interface MonteCarloHistogramBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface MonteCarloEquityFan {
  steps: number[];
  p5: number[];
  p25: number[];
  p50: number[];
  p75: number[];
  p95: number[];
}

export interface MonteCarloResponse {
  system_id: number;
  n_iterations: number;
  seed: number;
  n_trades: number;
  horizon: number;
  ev_p5: number | null;
  ev_p25: number | null;
  ev_p50: number | null;
  ev_p75: number | null;
  ev_p95: number | null;
  p_ev_positive: number | null;
  ev_histogram: MonteCarloHistogramBin[];
  equity_fan: MonteCarloEquityFan;
}

export interface MonteCarloQuery {
  n?: number;
  seed?: number;
  horizon?: number;
}

// --- Phase 7: Live-Trading (Trades, Risk-Rechner, Venues, Kontostand) ---

export type LiveStage =
  | "setup_sighted"
  | "risk_calculated"
  | "order_placed"
  | "entry_filled"
  | "running"
  | "closed"
  | "cancelled";

export type EntryOrderType = "market" | "limit";

// Live-Trades nutzen break_even statt draw (|R| < 0.1 -> break-even).
export type LiveWinLoss = "win" | "loss" | "break_even";

export interface LiveTrade {
  id: number;
  // null = freier Trade ohne System-Zuordnung.
  system_id: number | null;
  system_name: string | null;
  venue_id: number | null;
  asset_setting_id: number | null;
  asset: string | null;
  stage: LiveStage;
  direction: Direction | null;
  entry_order_type: EntryOrderType | null;
  planned_entry: number | null;
  planned_stop: number | null;
  actual_entry: number | null;
  actual_stop: number | null;
  exit_price: number | null;
  position_size_coins: number | null;
  position_size_notional: number | null;
  leverage: number | null;
  implicit_leverage: number | null;
  exchange_leverage: number | null;
  risk_usd: number | null;
  risk_pct: number | null;
  risk_modifier: number | null;
  expected_loss: number | null;
  realized_pnl_usd: number | null;
  r_value: number | null;
  win_loss: LiveWinLoss | null;
  deviation_pct: number | null;
  fees_paid: number | null;
  funding_paid: number | null;
  slippage: number | null;
  balance_after: number | null;
  portfolio_size_at_creation: number | null;
  snap_entry_fee_pct: number | null;
  snap_exit_fee_pct: number | null;
  snap_min_position_size: number | null;
  snap_leverage_buffer: number | null;
  snap_upside_deviation_allowed_pct: number | null;
  snap_downside_deviation_allowed_pct: number | null;
  snap_max_leverage: number | null;
  snap_leverage_step: number | null;
  snap_min_order_value_usd: number | null;
  opened_at: string | null;
  setup_sighted_at: string | null;
  risk_calculated_at: string | null;
  order_placed_at: string | null;
  entry_filled_at: string | null;
  running_at: string | null;
  closed_at: string | null;
  cancelled_at: string | null;
  duration_seconds: number | null;
  rules_followed: boolean | null;
  chart_url: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LiveTradeListResponse {
  total: number;
  limit: number;
  offset: number;
  items: LiveTrade[];
}

export interface LiveMetrics {
  closed_count: number;
  open_count: number;
  total_pnl_usd: number;
  total_r: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  avg_deviation_pct: number | null;
  current_balance: number;
}

// POST /risk/calc — genau eines von desired_risk_usd / risk_pct.
export interface RiskCalcRequest {
  entry_price: number;
  stop_price: number;
  desired_risk_usd?: number;
  risk_pct?: number;
  portfolio_size?: number;
  venue_id?: number;
  asset?: string;
  risk_modifier?: number;
}

export interface RiskCalcResponse {
  direction: Direction;
  price_move: number;
  effective_desired_risk: number;
  portfolio_size: number;
  risk_pct: number;
  initial_pos_size: number;
  initial_notional: number;
  initial_fees: number;
  initial_exp_loss: number;
  adjusted_pos_size: number;
  adjusted_notional: number;
  adjusted_fees: number;
  adjusted_exp_loss: number;
  adjusted_risk: number;
  valid_risk: boolean;
  risk_lower_bound: number;
  risk_upper_bound: number;
  // Leverage required by the calculation, safety buffer included.
  leverage: number;
  entry_fee_pct: number;
  exit_fee_pct: number;
  // Lot-Size des Assets, mit der gerundet wurde.
  min_position_size: number;
  // Leverage-Trennung (Phase 7.1): reine Kennzahl vs. einstellbare Stufe.
  implicit_leverage: number;
  exchange_leverage: number | null;
  max_leverage: number | null;
  leverage_exceeds_max: boolean;
  // Wie weit das gerundete Risiko das Ziel ueber-/unterschreitet (%).
  risk_overshoot_pct: number;
  // Sichere Alternative eine Lot-Stufe kleiner.
  floor_pos_size: number;
  floor_risk: number;
  floor_valid: boolean;
  rounds_to_zero: boolean;
  min_order_value_usd: number | null;
  below_min_order_value: boolean;
  asset: string | null;
  settings_asset: string | null;
  settings_fallback: boolean;
}

// POST /live-trades — Live-Trade anlegen (höchstens eines von desired_risk_usd / risk_pct).
export interface LiveTradeCreatePayload {
  // null = freier Trade ohne System-Zuordnung.
  system_id: number | null;
  venue_id?: number;
  asset?: string;
  entry_order_type?: EntryOrderType;
  planned_entry?: number | null;
  planned_stop?: number | null;
  desired_risk_usd?: number;
  risk_pct?: number;
  risk_modifier?: number;
  portfolio_size?: number;
  notes?: string | null;
  chart_url?: string | null;
  run_risk_calc?: boolean;
}

export interface LiveTradeUpdatePayload {
  asset?: string;
  entry_order_type?: EntryOrderType;
  planned_entry?: number | null;
  planned_stop?: number | null;
  // Ausfuehrungs-Korrektur: actual_* ab Stufe entry_filled erlaubt (auch bei
  // closed), die Abschluss-Felder nur bei closed. Bei einem geschlossenen
  // Trade rechnet das Backend PnL/R/win_loss/deviation UND den Kontostand neu;
  // ein falscher Stufenzeitpunkt liefert HTTP 409.
  actual_entry?: number | null;
  actual_stop?: number | null;
  exit_price?: number | null;
  realized_pnl_usd?: number | null;
  fees_paid?: number | null;
  funding_paid?: number | null;
  chart_url?: string | null;
  rules_followed?: boolean | null;
  notes?: string | null;
}

export type TransitionTarget = Exclude<LiveStage, "setup_sighted">;

export interface TransitionPayload {
  target_stage: TransitionTarget;
  planned_entry?: number | null;
  planned_stop?: number | null;
  desired_risk_usd?: number;
  risk_pct?: number;
  risk_modifier?: number;
  portfolio_size?: number;
  entry_order_type?: EntryOrderType;
  actual_entry?: number | null;
  actual_stop?: number | null;
  exit_price?: number | null;
  realized_pnl_usd?: number | null;
  fees_paid?: number | null;
  funding_paid?: number | null;
  rules_followed?: boolean | null;
  note?: string | null;
}

export interface AssetSetting {
  id: number;
  venue_id: number;
  asset: string;
  entry_fee_pct: number;
  exit_fee_pct: number;
  min_position_size: number;
  max_leverage: number | null;
  leverage_step: number;
  min_order_value_usd: number | null;
  leverage_buffer: number;
  upside_deviation_allowed_pct: number;
  downside_deviation_allowed_pct: number;
  valid_from: string;
  created_at: string;
}

export interface Venue {
  id: number;
  name: string;
  notes: string | null;
  created_at: string;
  current_settings: AssetSetting | null;
}

export interface VenuesResponse {
  items: Venue[];
}

export interface AssetSettingCreatePayload {
  asset?: string;
  entry_fee_pct: number;
  exit_fee_pct: number;
  min_position_size: number;
  max_leverage?: number | null;
  leverage_step?: number;
  min_order_value_usd?: number | null;
  leverage_buffer?: number;
  upside_deviation_allowed_pct?: number;
  downside_deviation_allowed_pct?: number;
  valid_from?: string;
}

export type BalanceChangeType = "initial" | "trade_close" | "manual";

export interface AccountBalanceEntry {
  id: number;
  balance: number;
  delta: number | null;
  change_type: BalanceChangeType;
  live_trade_id: number | null;
  note: string | null;
  as_of: string;
  created_at: string;
}

export interface AccountBalanceResponse {
  current_balance: number;
  history: AccountBalanceEntry[];
}

export interface LiveTradesQuery {
  system_id?: number;
  stage?: LiveStage;
  open_only?: boolean;
  include_cancelled?: boolean;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

// --- E3: Strategy Designer (StrategyDefinition mirrors
// backend/app/strategy/definition.py one-to-one; see that file's docstring
// for the design rationale — rules are data, not code, so lookahead bias is
// unrepresentable and the definition round-trips through JSONB untouched). ---

export const STRATEGY_SCHEMA_VERSION = 1;

export type PriceField = "open" | "high" | "low" | "close" | "volume";

export type IndicatorKind =
  | "sma"
  | "ema"
  | "rsi"
  | "atr"
  | "stdev"
  | "highest"
  | "lowest"
  | "roc";

export interface ParameterSpec {
  value: number;
  lo?: number | null;
  hi?: number | null;
  step?: number | null;
  description?: string | null;
}

export interface ParamRef {
  param: string;
}

// Any place the definition accepts a number, it also accepts a parameter
// reference (substituted by the engine's resolve() before running).
export type StrategyNumber = number | ParamRef;

export function isParamRef(v: StrategyNumber): v is ParamRef {
  return typeof v === "object" && v !== null && "param" in v;
}

export interface PriceOperand {
  op: "price";
  field: PriceField;
  offset: number;
}

export interface IndicatorOperand {
  op: "indicator";
  id: string;
  offset: number;
}

export interface ConstOperand {
  op: "const";
  value: StrategyNumber;
}

export interface PositionOperand {
  op: "position";
  field: "bars_held" | "unrealised_r" | "entry_price" | "direction_sign";
}

export type Operand =
  | PriceOperand
  | IndicatorOperand
  | ConstOperand
  | PositionOperand;

export type Comparator =
  | "<"
  | "<="
  | ">"
  | ">="
  | "=="
  | "!="
  | "cross_above"
  | "cross_below";

export interface Comparison {
  node: "compare";
  left: Operand;
  cmp: Comparator;
  right: Operand;
}

export interface BoolNode {
  node: "all" | "any" | "not";
  terms: Condition[];
}

export type Condition = Comparison | BoolNode;

export interface IndicatorSpec {
  id: string;
  kind: IndicatorKind;
  source: PriceField;
  params: Record<string, StrategyNumber>;
}

export interface StopSpec {
  kind: "atr_multiple" | "percent" | "indicator" | "fixed_points";
  value: StrategyNumber;
  indicator_id?: string | null;
  breakeven_at_r?: StrategyNumber | null;
  trail_atr_multiple?: StrategyNumber | null;
}

export interface TargetSpec {
  kind: "r_multiple" | "percent" | "indicator";
  value: StrategyNumber;
  indicator_id?: string | null;
}

export interface RiskSpec {
  stop: StopSpec;
  target?: TargetSpec | null;
  max_bars_held?: number | null;
  max_concurrent_positions: 1;
}

export interface CostSpec {
  entry_fee_pct: number;
  exit_fee_pct: number;
  slippage_pct: number;
  funding_pct_per_day: number;
}

export interface StrategyDefinition {
  schema_version: number;
  name: string;
  description?: string | null;

  asset: string;
  timeframe: string;
  direction: "long" | "short" | "both";

  // Which carrier holds the entry/exit logic — see definition.py's docstring.
  rules: "declarative" | "python";
  python_source?: string | null;

  parameters: Record<string, ParameterSpec>;
  indicators: IndicatorSpec[];

  entry_long?: Condition | null;
  entry_short?: Condition | null;
  exit_long?: Condition | null;
  exit_short?: Condition | null;
  filters: Condition[];

  risk: RiskSpec;
  costs: CostSpec;
}

export interface StrategySummary {
  id: number;
  name: string;
  description: string | null;
  asset: string;
  timeframe: string;
  rules: "declarative" | "python";
  current_version: number;
  updated_at: string;
  last_backtest_at: string | null;
  last_total_r: number | null;
}

export interface StrategyVersion {
  version: number;
  definition: StrategyDefinition;
  note: string | null;
  created_at: string;
}

export interface StrategyDetail extends StrategySummary {
  definition: StrategyDefinition;
  versions: StrategyVersion[];
}

export interface StrategyCreatePayload {
  name: string;
  description?: string | null;
  definition: StrategyDefinition;
}

export interface StrategyUpdatePayload {
  definition: StrategyDefinition;
  note?: string;
}

export interface StrategyDuplicatePayload {
  name: string;
}

export interface StrategyValidateResponse {
  ok: boolean;
  errors: string[];
  definition?: StrategyDefinition;
}

export interface EngineTrade {
  entry_index: number;
  exit_index: number;
  entry_ts: string;
  exit_ts: string;
  direction: "long" | "short";
  entry_price: number;
  stop_price: number;
  exit_price: number;
  r_value: number;
  gross_r: number;
  cost_r: number;
  win_loss: string;
  bars_held: number;
  exit_reason: string;
  tag: string | null;
}

export interface BacktestRun {
  id: number;
  strategy_id: number;
  version: number;
  status: "ok" | "failed";
  error: string | null;
  bars: number;
  warnings: string[];
  // Der Backtest liefert dasselbe all/is/oos-Tripel wie jedes andere System,
  // nicht einen einzelnen Block: die IS/OOS-Trennung greift auch hier.
  metrics: SystemMetrics | null;
  trades: EngineTrade[];
  overrides: Record<string, number>;
  created_at: string;
}

export type BacktestRunSummary = Omit<BacktestRun, "trades">;

export interface BacktestRequestPayload {
  start?: string;
  end?: string;
  overrides?: Record<string, number>;
  persist?: boolean;
}

// --- Block designer: rule vocabulary (GET /strategies/schema mirrors
// backend/app/strategy/vocabulary.py's rule_vocabulary() one-to-one; it is
// everything the designer needs to build a valid declarative definition,
// derived from the schema itself rather than hand-copied). ---

export interface IndicatorParamMeta {
  name: string;
  label: string;
  default: number;
  min: number;
}

export interface IndicatorVocabEntry {
  kind: IndicatorKind;
  label: string;
  uses_source: boolean;
  params: IndicatorParamMeta[];
}

export interface ComparatorVocabEntry {
  op: Comparator;
  is_crossing: boolean;
  allows_offset: boolean;
  numeric_friendly: boolean;
}

export interface BoolNodeVocabEntry {
  node: "all" | "any" | "not";
  label: string;
  arity: "many" | "one";
}

export interface StopKindVocabEntry {
  kind: StopSpec["kind"];
  requires_indicator: boolean;
}

export interface TargetKindVocabEntry {
  kind: TargetSpec["kind"];
  requires_indicator: boolean;
}

// A rule "slot" is one of the definition's five condition trees. Position
// operands only make sense while a position may be open, so the backend
// refuses them (nested occurrences included) anywhere but exit_long/
// exit_short — "position state (...) is only available to exit rules".
// `allows_position` on each slot and `position_operand_slots` say the same
// thing two ways; the designer uses whichever is convenient at the call site.
export type RuleSlot = "entry_long" | "entry_short" | "exit_long" | "exit_short" | "filters";

export interface RuleSlotVocabEntry {
  slot: RuleSlot;
  label: string;
  allows_position: boolean;
}

export interface RuleVocabulary {
  schema_version: number;
  price_fields: PriceField[];
  timeframes: string[];
  directions: StrategyDefinition["direction"][];
  rule_carriers: StrategyDefinition["rules"][];
  indicators: IndicatorVocabEntry[];
  comparators: ComparatorVocabEntry[];
  operand_kinds: Operand["op"][];
  position_fields: PositionOperand["field"][];
  position_operand_slots: RuleSlot[];
  rule_slots: RuleSlotVocabEntry[];
  bool_nodes: BoolNodeVocabEntry[];
  stop_kinds: StopKindVocabEntry[];
  target_kinds: TargetKindVocabEntry[];
  cost_defaults: CostSpec;
}
