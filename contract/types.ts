/**
 * GreenOps Basel · data contract between backend (pipeline) and frontend (3D).
 * Single source of truth: if a field changes, change it here first.
 *
 * Backend writes the files to output/ (python -m pipeline.run);
 * the frontend reads them from web/public/data/ (same files, copied).
 * See contract/README.md for the rules and contract/examples/ for samples.
 */

export const SCHEMA_VERSION = "0.1" as const;

// ------------------------------------------------------------------ basics
export type ISODate = string;            // "2026-08-01"
export type ISODateTime = string;        // "2026-08-28T00:00:00+02:00" (Europe/Zurich)
export type LocationCode = "CH" | "DE" | "IE" | "EU";
export type Category = "cloud" | "server" | "ai" | "saas";
export type Currency = "CHF" | "EUR" | "USD";
export type ValueStatus =
  | "observed"              // as billed / measured
  | "derived_exact"         // computed with all inputs known
  | "derived_cross_source"  // taken from another source
  | "estimated"             // estimate with a range
  | "missing";              // not estimable (never shown as 0)

/** Every figure is an estimate: low / mid / high. Show mid, explain the range. */
export interface Range {
  low: number;
  mid: number;
  high: number;
}

/**
 * The three metrics of the case, plus cost in every display currency.
 * The frontend never converts currencies: it picks cost_chf / cost_eur / cost_usd.
 * kwh and co2_kg are null only while not computed yet (or not applicable).
 */
export interface Metrics {
  cost_chf: Range;
  cost_eur: Range;
  cost_usd: Range;
  kwh: Range | null;
  co2_kg: Range | null;     // location-based (must)
  co2_kg_market?: Range | null; // market-based (bonus A3)
}

/** «Every number opens» (B3): how a figure was computed. */
export interface Calc {
  formula: string;            // "kWh = GPU-h × kWh per GPU-h × PUE"
  inputs: CalcInput[];
  factor_ids: string[];       // → factors.json
  source_files: string[];     // e.g. ["azure_costs.csv"]
  row_count: number;          // source rows behind the figure
  value_status: ValueStatus;  // weakest status among the inputs
  issue_ids: string[];        // → quality.json issues (Q-0001 …)
  note?: string;
}

export interface CalcInput {
  name: string;
  value: number;
  unit: string;
  source: string;             // file, ticket or factor id
}

export type ScenarioId = "ch_consumption" | "ch_production"; // Swiss grid mix (B2)

export interface Meta {
  schema_version: typeof SCHEMA_VERSION;
  generated_at: ISODateTime;
  baseline: { start: ISODate; end: ISODate };
  scenario: ScenarioId;       // scenario of the numbers in this file
}

// ---------------------------------------------------------- summary.json
export interface SummaryFile {
  meta: Meta;
  baseline: Metrics;            // actual baseline year (what is submitted)
  baseline_recurring: Metrics;  // baseline minus one-off excess
  one_offs: OneOff[];
  target: {
    co2_reduction: number;      // 0.40
    cost_reduction: number;     // 0.25
    budget_chf: number;         // 16500
    chf_per_person_day: number; // 1100
  };
  breakdown: {
    by_category: Breakdown[];
    by_department: Breakdown[];
    by_location: Breakdown[];
    by_tool: Breakdown[];
  };
  flows: Flow[];                // cables: department room → data-centre island
  coverage: Partial<Record<ValueStatus, number>>; // share of baseline cost, sums to 1
  calc: Calc;
}

export interface OneOff {
  id: string;                   // "OO-1"
  resource_id: string | null;
  ticket: string | null;        // "T-1212"
  reason: string;
  excess: Metrics;              // amount above normal (negative for refunds)
}

export interface Breakdown {
  key: string;                  // "cloud" | "IT" | "DE" | "Data platform production"
  label: string;
  entity_id: string | null;     // link into entities.json when one exists
  metrics: Metrics;
  share: { cost: number; co2: number | null }; // 0..1 of the baseline
}

export interface Flow {
  from: string;                 // "dept:IT"
  to: string;                   // "loc:DE"
  metrics: Metrics;
}

// --------------------------------------------------------- entities.json
export type EntityKind =
  | "room"            // department in the Basel office      id "dept:<Department>"
  | "island"          // data-centre location / EU cloud     id "loc:<CH|DE|IE|EU>"
  | "resource"        // billed resource (rack)              id "res:<resource_id>"
  | "server"          // virtual server inside a resource    id "srv:<server_id>"
  | "license_group";  // seats of one product in one room    id "lic:<product>@<Department>"

export type EntityState = "normal" | "driver" | "waste" | "locked" | "handover" | "contradiction";

export interface Entity {
  id: string;
  kind: EntityKind;
  label: string;
  parent_id: string | null;     // srv → res, res → loc, lic → dept
  department: string | null;
  tool: string | null;
  category: Category | null;
  location: LocationCode | null;
  metrics: Metrics;             // baseline year
  utilisation: number | null;   // 0..1 (CPU, active seats, active hours: see calc)
  idle_ratio: number | null;    // 0..1 (running but not working)
  seats?: { purchased: number; active: number };  // license_group
  /** Shared resource (mapping «Overhead», or billed to several departments): department is null and
   *  this lists each department's share of the baseline cost, with the key that allocated it. */
  allocation?: Allocation[];
  fte?: number;                 // room
  /** Primary visual state. Precedence: locked > handover > contradiction > waste > driver > normal.
   *  A contradiction takes precedence only when material (above the materiality threshold,
   *  severity warn/handover); an immaterial one ranks below the other states. */
  state: EntityState;
  flags: EntityState[];         // every state that applies, including immaterial contradictions (always shown)
  finding_ids: string[];
  measure_ids: string[];
  limit_ids: string[];
  calc: Calc;
}

export interface Allocation {
  department: string;           // "Sales"
  share: number;                // 0..1 of the resource's baseline cost; shares sum to 1
  key: "row_tag" | "cost_center" | "mapping" | "fte"; // how the rows were allocated
}

export interface EntitiesFile {
  meta: Meta;
  entities: Entity[];
}

// ------------------------------------------------------- timeseries.json
export interface Point {
  t: ISODate;                   // first day of the month, or the day
  cost_chf: number;
  cost_eur: number;
  cost_usd: number;
  kwh: number | null;
  co2_kg: number | null;
  runtime_h?: number;           // clusters / servers
  active_h?: number;
  partial?: boolean;            // incomplete period (September 2026)
}

export interface Series {
  entity_id: string;
  granularity: "month" | "day"; // month for every entity; day only for res:dp-prod, res:dp-dev, res:gpu-ml
  points: Point[];
}

export interface TimeseriesFile {
  meta: Meta;
  series: Series[];
}

// --------------------------------------------------------- findings.json
export interface Finding {
  id: string;                   // "F-01"
  kind: "waste" | "driver" | "anomaly";
  title: string;                // "dp-dev runs 24 h, works 2 h"
  entity_ids: string[];
  evidence: Evidence[];         // the numbers that prove it
  severity: "high" | "medium" | "low";
  impact: Metrics;              // yearly amount at stake
  measure_ids: string[];
  calc: Calc;
}

export interface Evidence {
  statement: string;            // "average active use on weekdays"
  value: number;
  unit: string;
  source_files: string[];
}

export interface FindingsFile {
  meta: Meta;
  findings: Finding[];
  /** Impacts are amounts at stake, they can overlap: never sum them. */
  additivity_note: string;
}

// --------------------------------------------------------- measures.json
export type MeasureStatus = "ok" | "human" | "blocked"; // ✅ / 🧑 / ⛔
export type MeasureType =
  | "schedule" | "rightsize" | "decommission" | "licence"
  | "relocate" | "model_switch" | "pipeline" | "storage" | "other";

export interface Measure {
  id: string;                   // "M-01"
  title: string;
  description: string;          // what exactly changes, and when
  type: MeasureType;
  entity_ids: string[];
  finding_ids: string[];
  limit_ids: string[];          // protection windows / blocks it respects or hits
  effort_days: number;
  effort_chf: number;           // effort_days × 1100
  savings: Metrics;             // per year; costs valued at baseline-average FX rates
  status: MeasureStatus;
  owner_role: string;           // who decides ("Head of IT")
  reason: string;               // why human / blocked; empty for ok
  start_date: ISODate;          // when savings actually start (notice periods)
  in_package: boolean;          // chosen by the optimizer
  calc: Calc;
}

export interface Package {
  measure_ids: string[];
  effort_days: number;
  effort_chf: number;
  savings: Metrics;
  reduction: { cost: Range; co2: Range };     // share of the baseline, 0..1
  meets: { co2: boolean; cost: boolean; budget: boolean };            // at mid
  meets_at_low: { co2: boolean; cost: boolean };                      // robustness: met even with the least favourable factor set
}

/** Energy and CO2 of the tool's own LLM calls in the run that produced these results. */
export interface AiFootprint {
  calls: number;
  calls_by_purpose: Record<string, number>;   // e.g. advisor.reader, advisor.plan.r1
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;                       // incl. reasoning tokens
  reasoning_tokens: number;
  output_equivalent_tokens: number;
  kwh: Range;
  co2_kg: Range;
  formula: string;
  source: string;
  models: string[];
}

/** What the optimal package prioritises (chosen by the user; switching is instant, no AI involved). */
export type GoalId = "climate_first" | "best_value" | "francs_first";

/** Optimal package for one goal; key in MeasuresFile.packages = the goal id. Every goal reaches the thresholds even
 *  with pessimistic factors (safety margin, always on); otherwise feasible: false with a note. */
export type GoalPackage =
  | ({ goal: string; feasible: true; safety_met: boolean; note?: string } & Package)   // safety_met false → show the note
  | { goal: string; feasible: false; note: string };

/** A resource deliberately NOT reduced, and why («not everything unused may be switched off»). */
export interface KeptOn {
  target: string;                              // e.g. "srv:dr-failover", "st-backup"
  reason: string;
  constraint_id: string;
  source: { kind: "ticket" | "file" | "calendar" | "rule"; ref: string };
  entity_ids: string[];
}

/** When and how the analysis behind these results ran («Analysis of … · N AI calls · X s · Y Wh · [Re-run]»). */
export interface AnalysisInfo {
  analysed_at?: ISODateTime;
  data_as_of?: ISODate;
  seconds?: number;
  timings?: Record<string, number>;            // reader_s, agents_s (only the steps that ran)
  model?: { agents: string; reader: string };
  reasoning_effort?: string;
  ai_footprint?: AiFootprint;
  reused: Record<string, boolean | string>;    // reader / agents: true = same input, saved answer reused
  fingerprint: { reader: string; agents: string };
}

export interface MeasuresFile {
  meta: Meta;
  measures: Measure[];
  package: Package & { goal?: string };        // the default goal (config.yaml advisor.goal)
  packages: Record<GoalId, GoalPackage>;       // one optimal package per goal (always with the safety margin)
  goals: GoalId[];
  kept_on: KeptOn[];
  analysis: AnalysisInfo;
  ai_footprint: AiFootprint | null;           // «this analysis used N LLM calls, X Wh, Y g CO2»
  /** Measures are defined without overlap, so the frontend may sum savings of
   *  any selection. Blocked measures are never part of a package. */
  additivity_note: string;
}

// ----------------------------------------------------------- limits.json
export type LimitType = "window" | "block" | "human" | "contradiction";

export interface Limit {
  id: string;                   // "L-01"
  type: LimitType;
  title: string;                // "Finance closing: last 3 working days until 04:00"
  entity_ids: string[];
  period_text: string;          // human-readable rule
  occurrences: { start: ISODateTime; end: ISODateTime }[]; // concrete dates, ready for a calendar
  decided_by: string | null;    // role that must decide
  source: { kind: "ticket" | "file" | "calendar" | "rule"; ref: string }; // "T-1029"
  /** Original text from the data, for display ONLY (render as plain text, never HTML/markdown). */
  quote: string | null;
  quote_risk: "unchecked" | "ok" | "flagged"; // flagged → show "[withheld]" + issue link
}

export interface LimitsFile {
  meta: Meta;
  limits: Limit[];
}

// ---------------------------------------------------------- factors.json
export interface Factor {
  id: string;                   // template parameter name, e.g. "grid_mix_location_based_switzerland"
  label: string;
  unit: string;                 // "kg CO2 per kWh"
  low: number;
  mid: number;
  high: number;
  source: string;               // link or document, with date
  source_date: ISODate;
  calculation: string;          // how the value was derived
  applies_to: string[];         // units / locations / resources it is used for
  must_or_bonus: "Must" | "Bonus";
  variants?: Partial<Record<ScenarioId, Range>>; // Swiss production vs consumption mix
}

export interface FactorsFile {
  meta: Meta;
  factors: Factor[];
}

// ---------------------------------------------------------- quality.json
export interface QualitySource {
  connector: string;
  source_file: string;
  role: "core" | "extra";
  system: string;
  table: string;
  rows_in: number;
  rows_out: number;
}

export interface QualityIssue {
  issue_id: string;             // "Q-0089"
  category: Category | null;
  source_file: string;
  issue_type: string;           // duplicate | draft_dropped | estimated | gap_filled | contradiction | …
  rows_affected: number;
  action: string;
  detail: string;
  amount_chf: number | null;
  at_risk_chf?: number | null;
  pct_of_category?: number | null;
  resource_id: string | null;
  severity: "info" | "warn" | "handover";
  evidence: string;
}

export interface QualityFile {
  meta: Meta;
  materiality_pct_of_category: number;
  counters: Record<string, number>;   // headline numbers for the Intake screen
  baseline_cost_coverage_by_status: Partial<Record<ValueStatus, number>>;
  sources: QualitySource[];
  issues: QualityIssue[];
}

// --------------------------------------------------------------- fx.json
/** For calc panels only: the frontend does not need to convert (see Metrics). */
export interface FxFile {
  meta: Meta;
  source: string;
  baseline_avg: Record<string, number>;                 // "USD_CHF": 0.7945
  monthly: Record<ISODate, Record<string, number>>;     // "2026-08-01": { "USD_CHF": 0.8076, … }
}

// =================================================================== BONUS
// One block per bonus file (see bonus-plan.md). Each owner adds the type of
// their file here, plus a sample in contract/examples/, BEFORE building it, so
// the frontend can work on the sample in parallel.
//   forecast.json    A2 · Forecast            (track 1)
//   market.json      A3 · Market-based CO₂    (track 1) · also Metrics.co2_kg_market
//   scenarios.json   B2 · Swiss mix switch    (track 1) · full file set in output/ch_production/
//   montecarlo.json  B1 · Monte Carlo         (track 1)
//   clusters.json    A4 · Clustering          (track 2)
//   jobs.json        A5 · Carbon-aware        (track 2)
//   chat API         A1 · Assistant           (track 2) · ChatRequest / ChatResponse

// --------------------------------------------------------- market.json (A3)
export type MarketBasis = "residual_mix" | "attribute_mix_proxy" | "location_proxy";

export interface MarketFactor {
  basis: MarketBasis;
  kg_per_kwh: Range;
  calculation: string;
  source: { source: string } & Record<string, string | number>;
}

export interface MarketTotals {
  kwh: Range;
  co2_kg: Range;
  co2_kg_market: Range;
  market_basis_kwh: Partial<Record<MarketBasis, Range>>;
  calc: Calc; // factor_ids reference keys in MarketFile.factors
}

export interface MarketFile {
  meta: Meta;
  note: string;
  scope2_guidance: string;
  factors: Record<string, MarketFactor>;
  baseline: MarketTotals;
  by_provider: (MarketTotals & { provider: string | null })[];
  measure_savings: Record<string, { co2_kg_market: Range; reason: null; calc: Calc }
    | { co2_kg_market: null; reason: string }>;
}

// ------------------------------------------------------- forecast.json (A2)
export interface ForecastComparison {
  without: Metrics; // business as usual, including announced changes
  with: Metrics | null; // projection from already-optimized history; null when input is absent
}

export interface ForecastCalculations {
  total: Calc;
  by_category: Partial<Record<Category, Calc>>;
}

export interface OptimizedHistoryCoverage {
  status: "complete" | "partial" | "missing_package" | "no_supported_measures";
  applied_measure_ids: string[];
  requires_confirmation: string[];
  skipped: { id: string; reason: string }[];
}

export interface ForecastFile {
  meta: Meta;
  horizon: { start: ISODate; end_exclusive: ISODate };
  months: (ForecastComparison & { month: ISODate; by_category: Partial<Record<Category, ForecastComparison>> })[];
  events: { date: ISODate; resource_id: string; label: string; source: string }[];
  assumptions: {
    id: string;
    source: string;
    method: string;
    unit?: string;
    value?: Range;
    by_month?: Record<string, Range>;
  }[];
  calculations: { without: ForecastCalculations; with: ForecastCalculations | null };
  optimized_history?: OptimizedHistoryCoverage;
}

// ------------------------------------------------ bonus/candidates.json
/** Findings / measures proposed by bonus modules to the Step 5–6 owners.
 *  NOT read by the frontend: the owners merge what they accept into
 *  findings.json / measures.json. */
export interface CandidatesFile {
  meta: Meta;
  by_module: Record<string, { findings: Finding[]; measures: Measure[] }>; // key: "clusters", "carbon_aware", …
}

// ------------------------------------------------------- clusters.json (A4)
/** Behaviour groups of servers (srv:*) and data-platform clusters (res:dp-*).
 *  Mode «groups» in the scene: recolour members by group_id; outliers stay apart. */
export interface ClustersFile {
  meta: Meta;
  method: {
    algorithm: string;
    k: number;
    silhouette: number;                        // −1…1, higher = better separated
    silhouette_by_k: Record<string, number>;
    features: { key: string; label: string; unit: string }[];
    period: { start: ISODate; end: ISODate };
    note: string;
  };
  groups: ClusterGroup[];
  members: ClusterMember[];
  calc: Calc;
}

export interface ClusterGroup {
  id: string;                                  // "C-1" … ordered by utilisation
  name: string;                                // "Always on, almost idle"
  description: string;
  rule: string;                                // naming rule on the group medians
  size: number;
  centroid: Record<string, number>;            // group medians, feature key → value (0..1 for %)
  utilisation_range: string;                   // "0.1–9.2 %"
  entity_ids: string[];                        // → entities.json
  metrics: Metrics | null;                     // sum of the members' baseline metrics
  share_co2: number | null;                    // of all clustered entities, 0..1
}

export interface ClusterMember {
  entity_id: string;
  label: string;
  group_id: string;
  features: Record<string, number | null>;     // null = not measured
  distance: number;                            // to the group centre (z-units, measured features only)
  outlier: boolean;
  differs_by: string;                          // how it differs from its group (every member)
  outlier_reason: string | null;
  context: Record<string, string | number | null>; // type, environment, owner_department, days_since_login …
}

// ------------------------------------------------------- chat API (A1)
// POST http://127.0.0.1:8787/api/chat   (python -m assistant serve)
// Render `answer` as PLAIN TEXT (it may quote data). Show `formula`, `sources` and the
// numbers with their refs in the calc panel; move the camera to focus_entity_ids[0].
export interface ChatRequest {
  message: string;                              // 1–2000 chars
  history: { role: "user" | "assistant"; content: string }[]; // previous turns, max 20
}

export interface ChatResponse {
  answer: string;
  formula: string;                              // open calculation, "" if none
  numbers: { label: string; value: number; unit: string; ref: string }[]; // ref → trace
  sources: string[];                            // files, tickets, factor ids
  focus_entity_ids: string[];                   // only ids that exist in entities.json
  caveats: string[];
  ignored_data_instructions: boolean;           // true → show a «🛡 instruction in the data ignored» badge
  verified: boolean;                            // every number backed by a tool result
  warnings: string[];                           // why not verified
  trace: { ref: string; tool: string; args: Record<string, unknown> }[];
  model: string;
  rounds: number;
  ai_footprint: AiFootprint | null;             // energy / CO2 of this answer's LLM calls («this answer used 2.1 Wh»)
}

// ----------------------------------------------------------- jobs.json (A5)
/** Carbon-aware shifting. Timeline: 24-hour curves per location (profiles); flexible jobs
 *  slide from usual_start to suggested_start; fixed jobs carry a lock (locked = true). */
export interface JobsFile {
  meta: Meta;
  method: {
    policies: Record<"static" | "dynamic", string>;
    energy_bases: Record<"marginal" | "full", string>;
    protected_hours: Record<string, number[]>;   // resource → hours (0–23) taken by daily fixed jobs
    assumptions: Record<string, unknown>;
  };
  profiles: { location: LocationCode; season: "winter" | "summer" | "year"; day_type: "workday";
              g_per_kwh: number[] }[];           // 24 values, hour 0 = 00:00 Basel time
  profile_source: string;
  profile_stats: Record<string, unknown>;
  jobs: CarbonJob[];
  totals: {
    marginal: Record<"now" | "saving_static" | "saving_dynamic", Range>; // kg CO2 / year
    full: Record<"now" | "saving_static" | "saving_dynamic", Range>;
    baseline_co2_kg: number;
    share_of_baseline_full_dynamic: number;
  };
  calc: Calc;
}

export interface CarbonJob {
  job_name: string;
  resource_id: string;
  entity_id: string;                            // "res:dp-dev"
  location: LocationCode;
  window_type: "fixed" | "flexible" | "other";
  window_rule: string;                          // "within 24 h", "done by 06:00 (morning reports)" …
  runs: number;                                 // runs in the baseline year
  usual_start: string;                          // "12:00"
  avg_duration_h: number;
  shiftable: boolean;
  locked: boolean;                              // fixed window → lock icon
  reason: string | null;                        // why not shiftable
  suggested_start: string | null;
  suggested_day_type?: "workday" | "weekend" | "same day";
  relative_intensity?: Record<"now" | "static" | "dynamic", number>; // 1 = yearly average of the location
  kwh_per_run: Record<"marginal" | "full", Range> | null;
  co2_kg_year: Record<"marginal" | "full", Record<"now" | "saving_static" | "saving_dynamic", Range>> | null;
}

// ------------------------------------------------------ scenarios.json (B2)
/** Swiss mix switch. The toggle «consumption / production» swaps the Swiss grid factor:
 *  indicators use scenarios[s].package.reduction, the scene recolours from
 *  entities_co2_kg_production (consumption values = entities.json). The package is the
 *  same in both: chosen once (consumption mix), only its CO2 is re-valued. */
export interface ScenarioResult {
  grid_ch: Range;                                   // kg CO2 / kWh used for Zurich
  baseline: { kwh: Range; co2_kg: Range; co2_by_location: Record<LocationCode, Range> };
  package: {
    measure_ids: string[];
    savings_co2_kg: Range;
    reduction: { co2: Range; cost: Range };         // sorted low ≤ mid ≤ high
    meets: { co2: boolean; cost: boolean; budget: boolean };   // at mid
    meets_at_low: { co2: boolean; cost: boolean };             // at the least favourable factors
  };
  /** The same, for every feasible goal package of the optimiser (measures.json → packages); the mix toggle
   *  shows packages_by_goal[selected goal]. `package` = the recommended goal (measures.json → package.goal). */
  packages_by_goal: Partial<Record<GoalId, ScenarioResult["package"]>>;
  measures: { id: string; title: string; status: MeasureStatus; in_package: boolean; co2_kg: Range }[];
}

export interface ScenariosFile {
  meta: Meta;
  default: ScenarioId;
  scenarios: Record<ScenarioId, ScenarioResult>;
  holds_in_both: boolean;                           // package meets target + budget under both mixes (mid)
  conclusion: string;                               // one sentence for the panel
  entities_co2_kg_production: Record<string, Range>; // entity id → CO2 under the production mix
  calc: Calc;
}

// ---------------------------------------------------- montecarlo.json (B1)
/** «The package reaches −40 % CO2 in X % of scenarios»: histogram + big sentence + tornado. */
export interface MonteCarloSummary {
  p_meet: number;                                   // share of draws reaching the target, 0..1
  percentiles: Record<"p5" | "p25" | "p50" | "p75" | "p95", number>; // reduction, 0..1
  mean: number;
}

export interface MonteCarloFile {
  meta: Meta;
  n_draws: number;
  seed: number;
  scenario: ScenarioId;
  goal: GoalId;                                     // the recommended goal; top-level figures are for its package
  package: { measure_ids: string[]; effort_days: number; deterministic_mid: { co2: number; cost: number } };
  target: { co2: number; cost: number };
  budget_met: boolean;
  co2_reduction: MonteCarloSummary;
  cost_reduction: MonteCarloSummary;
  p_meet_both: number;                              // CO2 and cost and budget in the same draw
  baseline_co2_kg: Record<string, number>;          // percentiles
  package_savings_co2_kg: Record<string, number>;
  histogram: { metric: "co2_reduction"; edges: number[]; counts: number[]; target: number }; // edges: N+1 values (0..1)
  tornado: {                                        // sorted by swing, largest first
    factor: string; label: string; range: Range;
    reduction_at_low: number; reduction_at_mid: number; reduction_at_high: number; swing: number;
  }[];
  stress_all_factors_together: MonteCarloSummary;   // all factors at the same quantile (extreme)
  production_mix: MonteCarloSummary;                // same simulation, Swiss production mix (B2)
  /** Every feasible goal package on the SAME draws (fair comparison); by_goal[goal] equals the top level. */
  by_goal: Partial<Record<GoalId, {
    measure_ids: string[]; effort_days: number;
    co2_reduction: MonteCarloSummary; cost_reduction: MonteCarloSummary; p_meet_both: number;
    stress_all_factors_together: MonteCarloSummary;
  }>>;
  headline: string;
  calc: Calc;
}

// ------------------------------------------------------- insights.json (extra sources)
/** Evidence from the 15 extra sources, one card per topic (see docs/extra-sources.md).
 *  Cards are NOT measures: potentials are upper bounds, not additive with the package. */
export interface InsightCard {
  id: "powerbi" | "regions" | "data_catalog" | "logs" | "ci_builds" | "ai_agents" | "web_traffic"
    | "backups" | "closed_projects" | "project_footprint" | "m365";
  title: string;
  source_files: string[];
  headline: string;                               // one sentence for the card
  numbers: { label: string; value: number; unit: string }[];
  potential: {
    action: string;
    metrics: Metrics;                             // upper bound per year if acted on
    status: MeasureStatus;                        // ok / human / blocked
    decided_by: string | null;
    note: string;
  } | null;
  protected: string[];                            // what must not be touched, and why
  entity_ids: string[];                           // objects in the scene to highlight
  advisor_fact_ids: string[];                     // the facts the advisor gets for this topic
  calc: Calc;
  steps?: { step: string; status: MeasureStatus; decided_by: string | null; metrics: Metrics | null;
            fits?: boolean; note: string }[];     // powerbi: clean-up, then downsizing
  safety_rule?: string;                           // regions
  by_agent?: { agent: string; runs: number; retries_per_run: number; output_tokens: number }[];
  by_department?: { department: string; active_users_admin: number; licences_active: number;
                    licences_purchased: number; difference_active: number }[];   // m365
  energy_check?: { bottom_up_kwh: Range; baseline_kwh: number; consistent: boolean; baseline_changed: false;
                   sources: string[] };            // m365
  allocation_note?: string;                       // project_footprint
}

export interface PowerBiReport {
  report_id: string; report: string; department: string; type: string;
  class: "in_use" | "unused" | "duplicate" | "quarterly" | "protected";
  action: string; refreshes: number; refresh_hours: number; views: number; tickets: string[];
  parent_id: "res:pbi-kap";                       // screens on the Power BI rack
}

export interface RelocationOption {
  resource_id: string; entity_id?: string; provider: string; from: LocationCode; to: string;
  kwh?: number; co2_kg_saved: Range | null;       // null: no researched grid factor for that location
  cost_note?: string; note?: string;
}

export interface InsightsFile {
  meta: Meta;
  cards: InsightCard[];
  sources: { file: string; used_for: string[] }[];          // every extra source → where it is used
  powerbi: { reports: PowerBiReport[] };
  regions: {
    offered: Record<string, { locations: string[]; used: string[];
                              regions: { region: string; location: string; used: boolean }[] }>;
    options: RelocationOption[];                            // sorted by CO2 saved
    unused_regions: { provider: string; region: string; location: string; used: false }[];  // grey islands
  };
  closed_projects: { project_id: string; project: string; ended: ISODate; resources: string[]; metrics: Metrics }[];
  projects: { project_id: string; project: string | null; type: "internal" | "customer" | null; customer: string | null;
              status: string | null; rechargeable: "yes" | "partly" | "no" | null;
              direct: Metrics; allocated_by_hours: Metrics; total: Metrics }[];
  note: string;
}

// ---------------------------------------------------------------- local AI (advisory, local_ai.json)
// Could the company's own AI workloads run on open-weight models on hardware it has or can rent?
// Information only: no number in measures, summary or forecast is changed. A human decides.

export type LocalAiTier = "basic" | "standard" | "advanced";
/** Like Range, but a bound is null when there is no break-even within the horizon. */
export interface MonthRange { low: number | null; mid: number | null; high: number | null; }

export interface LocalAiWorkload {
  id: string;                     // "wl:office-assistant"
  label: string; resource_id: string; tool: string; why_private: string;
  tier: LocalAiTier;              // highest tier among task types with >= 20 % of the API cost
  tasks: { task_type: string; tier: LocalAiTier; cost_share: number; out_eq_tokens: number }[];
  models_today: string[];
  tokens_in: number; tokens_in_cache: number; tokens_out: number;
  out_eq_tokens: number;          // output + 0.1 x uncached input + 0.01 x cached input (as the energy engine)
  requests: number;
  peak_tps: number; peak_tps_year3: number;   // busiest day / office hours, without one-off events
  api: Metrics;                   // baseline year without one-offs
  calc: Calc;
}

export interface LocalAiModel {
  id: string; label: string; params_b: number; active_params_b: number | null; format: string;
  weights_gb: number; licence: string; commercial_use: boolean; context_k: number;
  tier: LocalAiTier; languages: string; quality_note: string;
  throughput: Record<string, Range>;          // GPU class -> batched tokens/s
  source: string; estimate: boolean;
}

export interface LocalAiHardware {
  id: string;                     // "hw:gpu-ml-01"
  label: string; provider: string; location: LocationCode; gpu: string; gpu_class: string;
  vram_gb: number; tdp_w: number; idle_w: Range; host_w: Range;
  billing: "hourly" | "monthly";
  price_chf_per_hour: Range | null; price_chf_per_month: Range | null;
  on_hours_per_year: number;      // hourly: office hours; monthly: 8,760
  extra_setup_days: number;
  owned: boolean; entity_id: string | null;   // "srv:gpu-ml-01"
  measure_ids: string[];          // measures it interacts with (e.g. M-04)
  pue_factor_id: string; grid_factor_id: string;
  note: string; source: string; estimate: boolean;
}

export interface LocalAiFit {
  id: string;                     // "<workload>|<model>|<hardware>"
  workload_id: string; model_id: string; hardware_id: string;
  feasible: boolean; reasons: string[];
  tps: Range | null; gpu_hours_per_year: Range | null;
  kwh_per_year: Range | null; co2_kg_per_year: Range | null;   // generation only, without idle
}

export interface LocalAiScenario {
  id: string;                     // "sc:hybrid@hw:gpu-ml-01", "sc:all@...", "sc:<workload>@..."
  label: string; hardware_id: string;
  workload_ids: string[]; kept_on_api: string[];
  peak_tps_year3: number;
  model_id: string | null; alternatives: string[];
  feasible: boolean; reasons: string[];
  // present only when feasible:
  utilisation?: number;           // GPU busy share of on-hours, year 1
  api_3y?: Metrics; local_3y?: Metrics; savings_3y?: Metrics;   // savings may be negative
  setup_chf?: Range; yearly_chf?: Range;
  breakeven_month?: MonthRange;   // low = earliest, high = latest; null = not within 36 months
  interacts_with?: { measure_id: string; title: string; in_package: boolean;
                     cost_chf_per_year: Range | null; note: string }[];
  pros?: string[]; cons?: string[];
  calc?: Calc;
}

export interface LocalAiFile {
  meta: Meta;
  advisory: true;
  horizon_years: number;          // 3
  note: string;
  catalog_date: ISODate;
  workloads: LocalAiWorkload[];
  models: LocalAiModel[];
  hardware: LocalAiHardware[];
  fits: LocalAiFit[];
  scenarios: LocalAiScenario[];
  best: { by_cost: string | null; by_co2: string | null;
          by_workload: { workload_id: string; fit: string | null }[] };
  assumptions: { id: string; label: string; value: number | Range | Record<string, number>;
                 unit: string; source: string; estimate: boolean }[];
}