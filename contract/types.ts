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
  meets_at_low: { co2: boolean; cost: boolean };                      // robustness
}

export interface MeasuresFile {
  meta: Meta;
  measures: Measure[];
  package: Package;
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
