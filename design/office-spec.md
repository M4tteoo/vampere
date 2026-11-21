# Office digital twin — design specification

Source of truth for generating the 3D environment of the fictitious Basel SME
(image AI → Tripo / Meshy → React Three Fiber). Every number in this document comes from
the case data in `data/case/` (sample data ALTYCA, sprintd Basel 2026, synthetic) unless marked *design choice*.

Reference date for counts: **August 2026** (last full month of the baseline year Sep 2025 – Aug 2026).

---

## 0. How to use this document

1. **Style frame first (one image).** Generate ONE isometric cutaway of the whole floor with §2 + §3 (prompt in §8.1).
   Pick the best result: it becomes the style reference for everything else.
2. **One image per room**, always attaching the style frame as image reference (prompts in §8.2).
3. **3D: generate a reusable asset kit, not seven full rooms** (§7). The kit is generated once in Tripo / Meshy
   and instanced many times by code (119 desks share one desk model).
   Full-room extraction (Tripo Agentic Canvas) is fine for exploration, but the final scene needs one model per object
   type with stable names and IDs (§6).
4. **Architecture (floors, walls, glass, doors) is built in code**, using the dimensions in §3. It is cheap and stays consistent.
5. **State-bearing parts (screens, status LEDs, licence badges, glow) are added in code** on top of the models,
   so every object can change state regardless of how the generated mesh looks.

### Important scope rule (from the case README)
The case covers **software, cloud, data and AI only**. «Not included: devices, printers, network hardware and own data centres.»
So in the office:
- a desk/monitor stands for a **licence seat** (Microsoft 365, Copilot, Claude, ChatGPT, SaaS) — not for device electricity;
- a wall screen stands for a **Power BI report** (cloud refreshes);
- an AI device / robot stands for an **AI tool or agent** (tokens in EU data centres);
- a console in a room stands for **cloud infrastructure owned by that department**; the physical server lives on the
  data-centre island (Zurich / Frankfurt / Dublin), linked by a cable. This keeps the location-based story intact:
  *decided in Basel, emitted where the data centre is.*

---

## 1. Facts extracted from the data (per department)

| Department | Cost center | FTE Aug 2026 | Microsoft 365 seats (purchased/active) | Copilot | Claude Team | ChatGPT Team | Power BI reports (of which <100 views/yr) |
|---|---|---|---|---|---|---|---|
| Consulting | 4000 | 43.3 | 43 / 37 | 36 / 23 | 20 / 17 | – | 11 (6) |
| Sales | 4100 | 21.5 | 21 / 19 | 18 / 11 | – | 12 / 1 | 5 (2) |
| Finance | 4200 | 12.8 | 13 / 11 | 11 / 5 | – | – | 9 (3) |
| Marketing | 4300 | 12.6 | 13 / 12 | 11 / 7 | 6 / 5 | 7 / 1 | 8 (2) |
| HR | 4400 | 6.4 | 6 / 6 | 5 / 2 | – | 4 / 0 | 5 (2) |
| IT | 4500 | 16.9 | 17 / 15 | 14 / 9 | 8 / 6 | – | 12 (5) |
| Management | 4900 | 6.4 | 6 / 6 | 5 / 3 | – | – | 10 (6) |
| **Total** | | **119.9** | **119 / 106** | **100 / 60** | **34 / 28** | **23 / 2** | **60 (26)** |

Sources: `extra/headcount.csv`, `saas_contracts.csv` and `ai_subscriptions.csv` (Final rows, month 2026-08-01), `extra/powerbi_usage.csv` (baseline year).

**SaaS seats per department, Aug 2026 (purchased / active)** — `saas_contracts.csv`

| Contract | Consulting | Sales | Finance | Marketing | HR | IT | Management |
|---|---|---|---|---|---|---|---|
| Chat tool | 34/24 | 17/12 | 10/7 | 10/7 | 5/4 | 14/10 | 5/4 |
| Video conferencing tool | 34/18 | 17/10 | 10/6 | 10/5 | 5/3 | 14/8 | 5/3 |
| Time tracking | 34/32 | 17/15 | 10/8 | 10/9 | 5/4 | 14/12 | 5/4 |
| Password manager | 34/32 | 17/16 | 10/9 | 10/9 | 5/5 | 14/12 | 5/5 |
| Knowledge base | 34/17 | – | – | – | 5/3 | 14/7 | – |
| Project management | 34/18 | – | – | – | – | 14/8 | – |
| Project scheduling | 34/20 | – | – | – | – | 14/8 | – |
| Ticket system | 34/23 | – | – | – | – | 14/9 | – |
| Note-taking tool | 34/16 | – | – | – | – | – | – |
| CRM platform | – | 17/10 | – | 10/6 | – | – | – |
| E-signature | – | 17/5 | 10/3 | – | – | – | – |
| Accounting software | – | – | 10/8 | – | – | – | – |
| HR software | – | – | 10/9 | – | 5/4 | – | 5/4 |
| Design tool | – | – | – | 8/3 | – | – | – |
| Survey tool | – | – | – | 10/1 | – | – | – |

**AI tools and agents per department (baseline year)** — `ai_usage.csv`, `extra/ai_agent_runs.jsonl`, `mapping_departments_tools.csv`

| Department | AI tools used (requests/yr, cost CHF/yr) | Agents (runs/yr, trigger) |
|---|---|---|
| Consulting | Office AI assistant (≈940k, ≈7,400) · Knowledge chatbot (≈73k, ≈180) | support-agent (16,607, per ticket) · research-agent (1,457, scheduled) |
| Sales | Office AI assistant (≈600k, ≈4,770) · Quote generator `ai-quote` (≈58k, ≈510) | sales-agent (3,383, per event) |
| Finance | Office AI assistant (≈300k, ≈2,380) | report-agent `ai-report` (371, scheduled; reports opened only ~9%) |
| Marketing | **Marketing text analysis `ai-marketing` (≈7.2M, ≈11,560 — largest AI item; «Classify» on a large model; loop incident T-1212)** · Office AI assistant (≈385k, ≈3,070) | – |
| HR | Office AI assistant (≈172k, ≈1,370) · Knowledge chatbot `ai-chatbot` owner (≈49k, ≈120) | – |
| IT | Office AI assistant (≈257k, ≈2,050) | code-agent (5,924, manual) |
| Management | Office AI assistant (≈128k, ≈1,020) | – |

**Cloud infrastructure owned by each department** — `mapping_departments_tools.csv`, `server_inventory.csv`

| Department | Owned resources (physical location) |
|---|---|
| Consulting | `dp-prod` data platform production (Zurich) · `dp-storage` (Zurich) · `st-proj` project file storage (Swiss hoster) · `gpu-ml-01` GPU server (Frankfurt, owner cost center 4000) |
| Sales | `st-archive` legacy project archive (Zurich) |
| Finance | `db-fin` finance database (Zurich) |
| Marketing | `web-cdn` web hosting and CDN (Swiss hoster) |
| HR | – (only `ai-chatbot`) |
| IT | `vm-app` 12 app servers (Zurich) · `vm-test` 12 test servers (Dublin) · 24 personal sandboxes `sbx-*` (Dublin) · `dr-failover` (Dublin) · `dp-dev` dev cluster (Frankfurt) · `st-backup` backup archive (Dublin) · `cicd` build runners (Dublin) · `logs` (Swiss hoster) · `pbi-kap` Power BI capacity (Zurich) · `net-egress` · `support` |
| Management | – (Power BI dashboards only) |
| Overhead (shared) | Microsoft 365 · AI subscriptions · Office AI assistant `ai-assistant` · other SaaS |
| No owner | `poc-ki-2024`, `migration-alt` + 8 sandboxes without cost center (orphans, Dublin) |

**Microsoft 365 usage, weekly average** — `extra/m365_usage.csv` (department «People» = HR)

| Department | Active users | Storage (GB) | Teams video min/week | Mails/week |
|---|---|---|---|---|
| Consulting | 37 | 1,931 | 2,547 | 2,266 |
| Sales | 19 | 966 | 1,261 | 1,177 |
| IT | 15 | 772 | 1,002 | 937 |
| Finance | 11 | 580 | 749 | 686 |
| Marketing | 11 | 578 | 755 | 685 |
| HR | 6 | 289 | 373 | 340 |
| Management | 6 | 289 | 381 | 361 |

**Projects and collaboration (hours, baseline year)** — `extra/projects.csv`, `extra/project_hours_monthly.csv` — used for adjacency:
Consulting ↔ Sales (customer projects P-005..P-010, pre-sales P-013), Sales ↔ Management (P-013), Consulting ↔ IT (data platform P-003),
IT ↔ Marketing (webshop P-002), HR ↔ Consulting (training P-014), Finance ↔ IT ↔ Management (general operations P-015).

**Protection rules that must be visible in the rooms** — `it_tickets.csv`
- Finance: month-end closing needs `dp-prod` until ~04:00 on the last 3 working days (T-1029); `pbi-07` «Legacy report receivables» needed by internal audit (T-1167).
- IT: `dr-failover` must run (T-1094); backup archive kept 10 years (T-1039, T-1195); test environments frozen during acceptance tests (T-1204).
- Consulting: quarterly model training on days 1–3 of each quarter uses `dp-dev` + `gpu-ml-01` (T-1053, T-1101).
- Marketing: campaign weeks bring expected AI peaks (T-1163) — not waste.
- AI licences are ordered per department, not per person (T-1128).

---

## 2. Style bible (global, applies to every image and asset)

**Target:** A handcrafted tiny diorama with chunky slabs and softly rounded silhouettes. Warm, calm, tactile, premium but friendly.
An interactive «digital twin» seen as a dollhouse cutaway.

- **Camera:** true orthographic isometric from the south-east, 45° azimuth and 35.264° elevation. The room and whole-office isometric previews use square pixels and 58 pixels per projected metre.
  Walls cut at ~1.2 m height (dollhouse cutaway) so the interiors are fully readable.
- **Geometry:** believable real-world proportions; slightly softened/rounded edges (2–4 cm bevels); simplified details.
  Not low-poly, not cartoon, not photoreal micro-detail.
- **Materials (matte, soft):** light oak floors; warm white plaster walls; light concrete in shared areas; frosted and clear glass partitions
  with thin black frames; wool and linen textiles; matte powder-coated metal. No glossy plastic, no chrome, no neon.
- **Architecture palette:** warm off-white `#F7F3EE`, oak `#E8D2B8`, sand `#D6BD9F`, charcoal `#3A3F47` for technical equipment,
  plants in muted green `#7FA88B`. Brand/selection accent: coral `#FF5A5F` (used sparingly, only for highlights in the app, not in the rooms).
- **Asset palette:** oak `#E6B980`, plaster `#F6E9D6`, graphite `#37454A` and leaf `#86AF82`. Muted enamel `#52857F` and clay `#C77F62` distinguish hero equipment. Furniture uses restrained profiles and quiet finishes.
- **Department accent colours** (only on 1–2 surfaces per room: an accent wall, chair fabric, rug):
  Consulting sage `#9DBFA8` · Sales terracotta `#D98C6A` · Marketing blush coral `#F2A7A0` · IT slate blue `#7F9CC2` ·
  Finance ochre `#D9B45A` · HR lilac `#B9A7D9` · Management deep teal `#4F7F86`.
- **Lighting:** soft late-morning daylight from large windows on the north and east facades, gentle ambient occlusion,
  soft long shadows, warm interior pendant lights at 2700–3000 K. No dramatic contrast.
- **Occupancy:** use the workstation screen to indicate an active seat. Keep the diorama free of people.
- **Building:** a converted light-industrial loft in Basel (*design choice*): concrete columns on a 7 m grid, large steel-framed windows,
  exposed ceiling not shown (cutaway). One floor, ~42 × 28 m.
- **Screens:** all monitor and wall-screen surfaces are plain flat panels (they will be replaced by live emissive materials in code).
- **Avoid:** sci-fi, holograms, RGB lighting, glossy surfaces, text/logos on screens, brand logos, clutter, printers or network gear as features.

---

## 3. Floor plan (metres, design choice)

The 42 × 28 m envelope contains a 12 m north row, a 3 m east–west corridor and a 13 m south row. The south-east entrance opens into Reception. A 2 m wide gallery along the east side of HR connects Reception to the main corridor. Coordinates below are measured east and south from the north-west corner.

| Space | X extent | Z extent | Size (m) | Area (m²) | Desks | Use of floor space |
|---|---|---|---|---:|---:|---|
| Consulting | 0–20 | 0–12 | 20 × 12 | 240 | 43 | Four bench banks with a transverse aisle, two window nooks and a project wall |
| Sales | 20–32 | 0–12 | 12 × 12 | 144 | 21 | Three rows, each split into four and three desks by a cross aisle, and two phone booths |
| Marketing | 32–42 | 0–12 | 10 × 12 | 120 | 13 | Two desk clusters, a creative table and a separate text-analysis station |
| IT | 0–15 | 15–28 | 15 × 13 | 195 | 17 | Dual-monitor benches and four pairs of cloud-owner racks |
| Finance | 15–24 | 15–28 | 9 × 13 | 117 | 13 | Two work rows, a filing wall and the four-seat closing table |
| Management | 24–32 | 15–28 | 8 × 13 | 104 | 6 | Workstations, lounge and ten-seat boardroom |
| HR | 32–40 | 15–22.5 | 8 × 7.5 | 60 | 6 | Six-seat bench and a glazed interview nook |
| Reception + kitchen | 32–42 | 22.5–28 | 10 × 5.5 | 55 | 0 | Welcome desk, waiting area and kitchen table near the south entrance |
| Main corridor | 0–42 | 12–15 | 42 × 3 | 126 | 0 | Benches, planters and shared-services totem |
| Entrance gallery | 40–42 | 15–22.5 | 2 × 7.5 | 15 | 0 | Passage between Reception and the main corridor |

The plan allocates all 1,176 m². Room areas account for chair clearance, floor-standing equipment and meetings. Licence badges occupy desk surfaces and reports occupy walls. Report panels share several wall faces, with at least 0.60 m between neighbouring panels on the same face. The north and east glazing includes solid mounting bays. The concrete column grid is 7 m.

## 4. Room specifications

Each room lists: purpose, layout, furniture, **interactive objects** (IDs used by the app — see §6), states, and accent.
Desk count = Microsoft 365 seats purchased (Aug 2026). Active and empty-paid seats are distinguished by the screen state.

### 4.1 Consulting — data & AI consultants (cost center 4000)
- **Purpose:** customer projects (data strategy, reporting, AI assistant, process analysis), owner of the production data platform.
- **Size / layout:** 20 × 12 m. Four double rows of back-to-back bench desks (11 + 11 + 11 + 10) = 43 workstations;
  a project wall with pinned plans on the west wall; a stand-up table for 6; two small meeting nooks with sofas by the north windows.
- **Furniture:** oak bench desks, sage-fabric task chairs, single 27" monitors, laptop stands, desk lamps, large plants between rows, low storage cabinets.
- **Distinctive objects (interactive):**
  - `seat:consulting:01..43` workstations — 37 occupied (M365 active), 6 empty.
  - **Data platform console** `dp-prod` — a standing console/kiosk with a large screen near the project wall (owner of the production platform; physical cluster on the Zurich island). Shows a calendar band with protected windows.
  - **GPU console** `gpu-ml` — small console labelled «AI lab» (owner cost center 4000; physical server on the Frankfurt island).
  - **Project file storage** `st-proj` and `dp-storage` — a tidy filing/storage cabinet unit with a status strip.
  - **Agent robots** `agent:support-agent` (busiest agent, ticket-triggered) and `agent:research-agent` — two small friendly desk robots on a shared table.
  - **AI assistant orb** `ai-assistant:consulting` + Knowledge chatbot use.
  - **Licence badges** on desks: Copilot 36 (23 active), Claude Team 20 (17 active).
  - **Wall-mounted reports** `pbi:consulting` — 11 small wall screens (6 rarely viewed: pbi-17, pbi-23, pbi-24, pbi-28, pbi-42, pbi-53).
- **Accent:** sage `#9DBFA8` on chair fabric and one wall.

### 4.2 Sales (cost center 4100)
- **Purpose:** pre-sales, quotes, CRM, customer accounts.
- **Size / layout:** 12 × 12 m. Three rows of 7 desks = 21 workstations; two acoustic phone booths by the corridor; a small pipeline board.
- **Furniture:** oak desks, terracotta chairs, monitors, headsets on stands, acoustic felt panels.
- **Distinctive objects (interactive):**
  - `seat:sales:01..21` — 19 occupied, 2 empty.
  - **CRM terminal** `saas:crm-platform:sales` (17 seats / 10 active) and **e-signature tablet stand** `saas:e-signature:sales` (17 / 5).
  - **Quote generator device** `ai-quote` and **sales agent robot** `agent:sales-agent`.
  - **Archive cabinet** `st-archive` — «legacy project archive» (physical storage on the Zurich island).
  - **Licence badges:** Copilot 18 (11 active), **ChatGPT Team 12 (1 active)** — the ChatGPT badges are almost all dark.
  - **Wall-mounted reports** `pbi:sales` — 5 screens (2 rarely viewed: pbi-10, pbi-12).
- **Accent:** terracotta `#D98C6A`.

### 4.3 Marketing (cost center 4300)
- **Purpose:** campaigns, webshop and website content, customer surveys.
- **Size / layout:** 10 × 12 m. Two clusters of desks (7 + 6) = 13 workstations; a large creative table with mood boards;
  a small photo/content corner with a backdrop; east-facing windows.
- **Furniture:** oak desks, blush-coral chairs, large monitor for design work, pin boards, plants, colourful but muted rug.
- **Distinctive objects (interactive):**
  - `seat:marketing:01..13` — 12 occupied, 1 empty.
  - **Text-analysis machine** `ai-marketing` — the most important AI object in the building: a distinctive console/«sorting machine»
    that visibly processes items. Largest AI cost; uses a large model for simple classification; once ran in an endless loop (T-1212).
  - **Website / webshop screen** `web-cdn` (Swiss hoster; ~39% of traffic is bots).
  - **Survey kiosk** `saas:survey-tool:marketing` (10 seats / 1 active) and **design tablet** `saas:design-tool:marketing` (8 / 3).
  - **Licence badges:** Copilot 11 (7), Claude Team 6 (5), ChatGPT Team 7 (1).
  - **Wall-mounted reports** `pbi:marketing` — 8 screens (2 rarely viewed: pbi-06 «Marketing campaigns 2024», pbi-09 «Customer survey 2024»).
- **Accent:** blush coral `#F2A7A0`.

### 4.4 IT (cost center 4500)
- **Purpose:** operations, development, cloud administration — owns most of the infrastructure.
- **Size / layout:** 15 × 13 m. 17 workstations in two rows of dual-monitor desks; a **monitoring wall** facing the room;
  a «cloud control» corner with one small network cabinet (decor) and the consoles below; whiteboard; spare-parts shelf.
- **Furniture:** oak desks, slate-blue chairs, dual monitors, a large wall display, cable trays kept tidy.
- **Distinctive objects (interactive):** each console is the «owner view» of a resource that physically runs on an island.
  - `seat:it:01..17` — 15 occupied, 2 empty.
  - **Monitoring wall** `pbi-kap` + `logs` — large screen.
  - **Rack consoles** (one compact rack-shaped kiosk each): `vm-app` (12 app servers, Zurich), `vm-test` (12 test servers, Dublin),
    `sandboxes` (24 personal sandboxes, Dublin), `dp-dev` (dev cluster, Frankfurt), `dr-failover` (Dublin, **must run**),
    `st-backup` (Dublin, **10-year retention**), `cicd` (build runners, Dublin), `orphans` (poc-ki-2024, migration-alt, build-agent-old).
  - **Code agent robot** `agent:code-agent`.
  - **Licence badges:** Copilot 14 (9), Claude Team 8 (6).
  - **Wall-mounted reports** `pbi:it` — 12 screens (5 rarely viewed incl. pbi-08 «Test report AI pilot»).
- **Accent:** slate blue `#7F9CC2`.

### 4.5 Finance (cost center 4200)
- **Purpose:** accounting, month-end and year-end closing, budgets, liquidity.
- **Size / layout:** 9 × 13 m. 13 workstations in two rows; a filing wall (closed cabinets); a quiet closing table for 4; a wall calendar.
- **Furniture:** oak desks, ochre chairs, monitors, closed cabinets, desk lamps.
- **Distinctive objects (interactive):**
  - `seat:finance:01..13` — 11 occupied, 2 empty.
  - **Finance database console** `db-fin` (Zurich).
  - **Closing calendar** `window:finance-closing` — a wall calendar highlighting the last 3 working days of each month (protects `dp-prod`).
  - **Audit screen** `pbi-07` — «Legacy report receivables», rarely viewed but **locked** (internal audit).
  - **Report agent robot** `agent:report-agent` — produces reports that are opened only ~9% of the time.
  - **E-signature tablet** `saas:e-signature:finance` (10 / 3), **accounting terminal** `saas:accounting-software:finance` (10 / 8).
  - **Licence badges:** Copilot 11 (5).
  - **Wall-mounted reports** `pbi:finance` — 9 screens (3 rarely viewed: pbi-15, pbi-29, pbi-33).
- **Accent:** ochre `#D9B45A`.

### 4.6 HR (cost center 4400)
- **Purpose:** recruiting, training, people administration.
- **Size / layout:** 8 × 7.5 m. 6 workstations; a small private interview room (glass, frosted); a soft seating corner.
- **Furniture:** oak desks, lilac chairs, sofa, plants, closed cabinets.
- **Distinctive objects (interactive):**
  - `seat:hr:01..06` — 6 occupied.
  - **Knowledge chatbot kiosk** `ai-chatbot` (HR is the owner; also used by Consulting).
  - **HR software terminal** `saas:hr-software:hr` (5 / 4).
  - **Licence badges:** Copilot 5 (2), **ChatGPT Team 4 (0 active)**.
  - **Wall-mounted reports** `pbi:hr` — 5 screens (2 rarely viewed incl. pbi-30 «Liquidity HR 30 (copy)»).
- **Accent:** lilac `#B9A7D9`.

### 4.7 Management (cost center 4900)
- **Purpose:** leadership, budget and strategy; decides on hand-overs.
- **Size / layout:** 8 × 13 m. 6 workstations; a boardroom with a 10-seat table and a large wall screen; a small lounge.
- **Furniture:** oak and walnut details, deep-teal chairs, boardroom table, sideboard, large plant.
- **Distinctive objects (interactive):**
  - `seat:management:01..06` — 6 occupied.
  - **Boardroom display and wall-mounted reports** `pbi:management` — 10 dashboards (6 rarely viewed, several «(copy)»: pbi-13, pbi-25, pbi-31, pbi-37, pbi-50, pbi-55).
  - **Approval desk** `handover:queue` — where measures that need a human decision land (Head of IT, Head of Finance…).
  - **Licence badges:** Copilot 5 (3).
- **Accent:** deep teal `#4F7F86`.

### 4.8 Shared spaces (decor, not interactive)
- **Corridor:** 3 m wide, planters, two benches, a large window at each end.
- **Reception + kitchen/lounge:** reception desk, sofa, coffee bar, long table. Main entrance on the south façade.
- Optional interactive anchor: **Microsoft 365 hub** `saas-m365` + `m365-usage` as a «shared services» totem in the corridor
  (Overhead: M365, chat, video conferencing, password manager, time tracking).

---

## 5. Data-centre islands (outside the building)

Unchanged from the current prototype: floating islands for **Zurich** (CH), **Frankfurt** (DE), **Dublin** (IE) and a cloud for **EU (mixed)** AI/SaaS providers.
They host the *physical* infrastructure. Each room console is linked to its island object by a cable.

| Island | Physical objects |
|---|---|
| Zurich | `dp-prod` (cluster), `vm-app` (12), `db-fin`, `pbi-kap`, `dp-storage`, `st-archive`, (+ `dp-dev` when moved by measure M1) |
| Frankfurt | `dp-dev` (cluster), `gpu-ml` (GPU server) |
| Dublin | `vm-test` (12), sandboxes (24), `orphans` (3), `dr-failover`, `st-backup`, `cicd` |
| Swiss hoster (on the Zurich island, separate pad) | `logs`, `st-proj`, `web-cdn` |
| EU (mixed) | AI APIs (`ai-assistant`, `ai-marketing`, `ai-quote`, `ai-chatbot`, agents), AI subscriptions, SaaS |

---

## 6. Interactive object registry (contract for the app)

Every object that influences cost, energy or CO₂ has a **stable ID**, a **room** (owner view) and, if it is infrastructure, an **island** (physical view).
These IDs match `resource_id` in the data wherever possible, so the backend can join them.

| ID pattern | Represents | Count | Where | Data source | States |
|---|---|---|---|---|---|
| `seat:<dept>:NN` | Microsoft 365 seat / workstation | 119 | rooms | `saas_contracts.csv` (Microsoft 365), `extra/m365_usage.csv` | occupied · empty-paid (waste) · removed |
| `lic:<product>:<dept>` | AI subscription seats (copilot, claude, chatgpt) as desk badges | 157 badges in 13 groups | rooms | `ai_subscriptions.csv` | active · inactive (dim) · cancelled |
| `saas:<contract>:<dept>` | SaaS contract seats (one device/terminal per contract and department) | 48 groups | rooms | `saas_contracts.csv` | normal · under-used (waste) · right-sized |
| `pbi-01..60` | Power BI reports as wall screens (grouped as `pbi:<dept>`) | 60 | rooms | `extra/powerbi_usage.csv`, mapping | viewed · refreshing-unwatched (waste) · locked (`pbi-07`) · off |
| `ai-assistant`, `ai-marketing`, `ai-quote`, `ai-chatbot` | AI applications via API | 4 (+ per-dept assistant orbs) | rooms + EU cloud | `ai_usage.csv` | normal · spike/loop · downsized (small model) |
| `agent:<name>` | AI agents (support, research, sales, code, report) | 5 | rooms + EU cloud | `extra/ai_agent_runs.jsonl` | running · retrying · output unused |
| `dp-prod`, `dp-dev`, `gpu-ml`, `vm-app`, `vm-test`, `sandboxes`, `orphans`, `dr-failover`, `db-fin`, `pbi-kap`, `st-backup`, `st-archive`, `st-proj`, `dp-storage`, `cicd`, `logs`, `web-cdn`, `net-egress` | Cloud infrastructure | 18 | console in owner room + object on island | cloud invoices, `server_inventory.csv`, `server_metrics_weekly.csv`, `data_platform_usage.csv` | active · idle-waste · reduced · off · moved · locked · needs-human |
| `window:<name>` | Protection windows (calendar objects) | 4 | Finance, Consulting, IT | `it_tickets.csv`, `extra/data_platform_jobs.csv`, `business_calendar.csv` | info only |
| `handover:queue` | Measures waiting for a human decision | 1 | Management | measures engine | empty · pending |

**3D contract.** Each `kit_<object>_v1.glb` exposes static geometry as `body`. The meshes and empty attachment nodes listed in §7 retain their names when exported. Resource IDs belong to instances in the app. The dual monitor uses `screen` on the left and `screen_2` on the right as seen from the front, with matching overlay anchors. Chair upholstery and robot shells use the light neutral grey `accent` mesh. The belt and fan each have a centred pivot along local +Z in glTF; the app drives motion and screen content.

---

## 7. Reusable asset kit (generate once, instance many times)

All dimensions are in metres. GLBs are Y-up, face +Z, and use the centre of the footprint at floor level as the asset origin. Tabletop objects use their contact surface as floor level. Overlay anchors share the asset coordinates. The desk badge anchor sits on the right side of the top; the approval label anchor sits above the in-tray.

The 36 active generators share 15 named materials in `design/blender/kit/common.py`. Warm oak, walnut and plaster carry the furniture, and enamel, clay and graphite distinguish the interactive equipment. Screens use plain dark grey. Licence and resource state are applied at runtime. Dimensions and budgets for objects newly introduced in this kit are design choices.

| Asset | Used for | Real size (w × d × h), m | Triangles / budget | Runtime meshes and overlay anchors |
|---|---|---|---:|---|
| `kit_desk_bench` | 119 licence-seat workstations | 1.4 × 0.75 × 0.74 | 416 / 2,500 | `anchor_badge` |
| `kit_chair_task` | Department-tinted workstation chairs | 0.6 × 0.6 × 1 | 924 / 3,000 | `accent` |
| `kit_monitor_27` | Single-monitor workstations | 0.62 × 0.2 × 0.5 | 208 / 800 | `screen`, `anchor_screen` |
| `kit_monitor_dual` | IT workstations | 1.25 × 0.25 × 0.5 | 516 / 1,500 | `screen`, `screen_2`, `anchor_screen`, `anchor_screen_2` |
| `kit_licence_puck` | 157 AI licence badges | 0.105 × 0.105 × 0.032 | 142 / 150 | `status_led`, `anchor_led` |
| `kit_console_kiosk` | Owner consoles for dp-prod, gpu-ml and db-fin | 0.6 × 0.5 × 1.4 | 536 / 1,500 | `screen`, `status_led`, `anchor_led`, `anchor_screen` |
| `kit_rack_compact` | Eight IT owner consoles | 0.6 × 0.8 × 1.2 | 1,332 / 2,000 | `status_led`, `anchor_led` |
| `kit_storage_cabinet` | st-proj, dp-storage and st-archive | 0.9 × 0.48 × 0.98 | 812 / 1,100 | `status_led`, `anchor_led` |
| `kit_wall_screen` | Power BI reports and web-cdn | 1.2 × 0.06 × 0.7 | 120 / 400 | `screen`, `anchor_screen` |
| `kit_wall_screen_large` | IT pbi-kap and logs, Management dashboards | 2.4 × 0.1 × 1.35 | 120 / 500 | `screen`, `anchor_screen` |
| `kit_ai_orb` | Department ai-assistant instances and HR ai-chatbot | 0.4 × 0.4 × 0.5 | 884 / 1,500 | `glow` |
| `kit_text_machine` | Marketing text analysis | 1.6 × 0.8 × 1.3 | 2,152 / 5,000 | `belt`, `glow` |
| `kit_quote_device` | Sales ai-quote | 0.38 × 0.3 × 0.24 | 480 / 850 | `status_led`, `anchor_led` |
| `kit_agent_robot` | Five agent instances | 0.35 × 0.3 × 0.5 | 1,372 / 3,000 | `accent`, `face_screen`, `status_led`, `anchor_led`, `anchor_screen` |
| `kit_saas_terminal` | CRM, accounting and HR software | 0.45 × 0.34 × 0.43 | 288 / 900 | `screen`, `anchor_screen` |
| `kit_tablet_stand` | E-signature, survey and design software | 0.3 × 0.3 × 1.1 | 240 / 800 | `screen`, `anchor_screen` |
| `kit_wall_calendar` | Finance closing window | 1.2 × 0.05 × 0.9 | 218 / 300 | `days` |
| `kit_approval_desk` | Management handover queue | 1.45 × 0.75 × 0.85 | 836 / 1,500 | `anchor_label` |
| `kit_m365_totem` | Corridor shared services | 0.56 × 0.44 × 1.7 | 540 / 1,300 | `screen`, `status_led`, `anchor_led`, `anchor_screen` |
| `kit_phone_booth` | Sales calls | 1.1 × 1.1 × 2.2 | 920 / 3,000 | — |
| `kit_creative_table` | Marketing studio worktable | 2.4 × 1.1 × 0.9 | 848 / 1,500 | — |
| `kit_pinboard` | Marketing material studies | 1.8 × 0.1 × 1.9 | 288 / 600 | — |
| `kit_project_wall` | Consulting project plans | 2.1 × 0.1 × 1.3 | 456 / 800 | — |
| `kit_whiteboard` | IT planning | 1.8 × 0.1 × 1.9 | 316 / 600 | — |
| `kit_cabinet_tall` | Finance filing wall | 0.8 × 0.45 × 2 | 328 / 600 | — |
| `kit_sofa_2` | HR and shared lounges | 1.6 × 0.85 × 0.8 | 1,608 / 3,000 | — |
| `kit_armchair` | HR interviews and lounges | 0.8 × 0.8 × 0.8 | 1,308 / 3,000 | — |
| `kit_board_table_10` | Management boardroom | 4 × 1.4 × 0.74 | 356 / 1,500 | — |
| `kit_reception_desk` | Welcome counter | 2.4 × 0.8 × 1.1 | 588 / 3,000 | — |
| `kit_coffee_bar` | Shared kitchen | 2.4 × 0.8 × 1.1 | 932 / 3,000 | — |
| `kit_bench` | Corridor seating | 1.55 × 0.43 × 0.46 | 336 / 700 | — |
| `kit_plant_large` | Room dividers and lounges | 0.7 × 0.7 × 1.6 | 1,868 / 4,000 | — |
| `kit_plant_small` | Reception and meeting spaces | 0.3 × 0.3 × 0.5 | 1,256 / 1,500 | — |
| `kit_server_rack_42u` | Island compute clusters | 0.6 × 1 × 2 | 1,528 / 3,000 | `status_led`, `anchor_led` |
| `kit_gpu_server` | Frankfurt GPU | 0.9 × 0.8 × 1.1 | 1,046 / 3,000 | `fan`, `status_led`, `anchor_led` |
| `kit_storage_array` | Island storage, backup and archive | 0.9 × 0.7 × 1.2 | 992 / 2,000 | `status_led`, `anchor_led` |

Earlier design options outside the active kit include the laptop stand (0.35 × 0.25 × 0.2 m, 800 triangles), low cabinet (0.8 × 0.45 × 0.75 m, 600 triangles) and six-seat meeting table (2.4 × 1.1 × 0.74 m, 1,500 triangles).

Total scene budget target: ≤ 300k triangles on screen with instancing (119 × (desk + chair + single monitor) = 184,212 triangles with the current kit).

---

## 8. Prompts

### 8.1 Style frame — whole floor (image AI)

```
Isometric dollhouse cutaway of a single-floor office of a 120-person data and AI consulting company in Basel, Switzerland.
Converted light-industrial loft, 42 x 28 m, concrete columns, large steel-framed windows on the north and east facades,
walls cut at 1.2 m height so every room is visible from above. No ceiling.

Layout (north at top): north row — Consulting (large open space, ~43 bench desks), Sales (21 desks, two acoustic phone booths),
Marketing (13 desks, creative table with mood boards). A 3 m corridor with planters runs east–west through the middle.
South row — IT (17 dual-monitor desks), Finance (13 desks), Management (6 desks and a ten-seat boardroom).
At the east end, HR (6 desks and an interview room) sits north of Reception and the kitchen lounge.
An entrance gallery connects the reception to the main corridor.

Style: Airbnb-inspired stylized architectural visualization, warm and calm, believable proportions, softly rounded edges,
matte materials. Light oak floors, warm white walls, glass partitions with thin black frames, wool and linen textiles,
plants in muted green. Each department has one subtle accent colour on chairs and one wall: Consulting sage, Sales terracotta,
Marketing blush coral, IT slate blue, Finance ochre, HR lilac, Management deep teal.
Soft late-morning daylight, gentle ambient occlusion, soft shadows, warm pendant lights.
Active workstations have lit screens. Keep the floor free of people.
All screens are blank flat panels. No text, no logos, no sci-fi, no neon, no glossy plastic, no clutter.
3/4 isometric view, 35 degrees elevation, orthographic look, high resolution, clean background #F7F3EE.
```

### 8.2 Room images (attach the chosen style frame as reference)

Use the master template and replace `[ROOM]` with the room block below.

```
Same building, same visual style, same materials and lighting as the reference image.
Isometric dollhouse cutaway of ONE room, walls cut at 1.2 m, 3/4 view 35 degrees elevation, orthographic look,
background #F7F3EE, all screens blank, no text, no logos.

[ROOM]

Keep every object clearly separated with visible space around it (it will be converted into separate 3D models).
```

- **Consulting:** `Consulting open space, 20 x 12 m, four rows of oak bench desks back-to-back (43 workstations), single 27-inch monitors, sage-green task chairs, desk lamps, large plants between rows. West wall: a project wall with pinned plans. Near it: a standing console with a large screen (data platform) and a smaller console (AI lab). A tidy storage cabinet unit. A shared table with two small friendly desk robots. Two sofa nooks by the north windows. 37 active desks, 6 empty desks.`
- **Sales:** `Sales office, 12 x 12 m, three rows of 7 oak desks, terracotta chairs, headsets on stands, two acoustic felt phone booths by the glass corridor wall, a small pipeline board, one tablet on a stand (e-signature), one CRM terminal, a small device for quote generation, one small friendly robot, a tall archive cabinet. 19 active desks, 2 empty desks.`
- **Marketing:** `Marketing studio, 10 x 12 m, two clusters of oak desks (7 and 6), blush-coral chairs, a large creative table with mood boards and pin boards, a small content corner with a backdrop. A distinctive compact "sorting machine" console with a short conveyor belt and a soft glow (AI text analysis). A website screen, a survey kiosk on a stand, a design tablet. East windows. 12 active desks, 1 empty desk.`
- **IT:** `IT operations room, 15 x 13 m, two rows of oak desks with dual monitors (17 workstations), slate-blue chairs, a large monitoring wall facing the desks, a "cloud control" corner with four separated pairs of compact rack-shaped kiosks with small status lights, one small network cabinet, a whiteboard, a spare-parts shelf, one small friendly robot. Tidy cable trays. 15 active desks, 2 empty desks.`
- **Finance:** `Finance office, 9 x 13 m, two rows of oak desks (13 workstations), ochre chairs, a wall of closed filing cabinets, a quiet closing table for 4, a large wall calendar, one standing console with a screen (finance database), one wall screen, a tablet stand, one small friendly robot. 11 active desks, 2 empty desks.`
- **HR:** `HR office, 8 x 7.5 m, 6 oak desks, lilac chairs, a small frosted-glass interview room with two armchairs, a soft seating corner with a sofa and plants, a kiosk with a soft glowing orb (knowledge chatbot), a terminal on a stand. 6 active desks.`
- **Management:** `Management area, 8 x 13 m, 6 oak desks with walnut details, deep-teal chairs, a glass boardroom with a 10-seat table and a large wall screen, a small lounge with two armchairs, a sideboard and a large plant, a small approval desk with an in-tray. 6 active desks.`

### 8.3 Tripo / Meshy — single assets (image-to-3D or text-to-3D)

Crop the object from the room image, or use the text below. Always append the suffix.

```
Suffix: stylized realistic, softly rounded edges, matte materials, clean simple topology for real-time web use,
single object, centered, no base, no background, no text, no logos, neutral studio light, real-world scale.
```

| Asset | Text prompt (before the suffix) |
|---|---|
| `kit_desk_bench` | Modern office desk, light oak top 140 × 75 cm, thin matte charcoal metal legs, cable tray underneath |
| `kit_chair_task` | Ergonomic office task chair, upholstered seat and back in plain fabric, matte charcoal base with five wheels |
| `kit_monitor_27` | 27-inch computer monitor on a slim stand, thin bezel, blank screen |
| `kit_wall_screen` | Slim wall-mounted display, thin frame, blank screen |
| `kit_console_kiosk` | Standing information kiosk with a tilted large screen and a small status light strip, oak and white |
| `kit_rack_compact` | Compact half-height server rack cabinet, matte charcoal, perforated front door, small status light strip |
| `kit_server_rack_42u` | Full-height server rack, matte charcoal, perforated front door, row of small status lights |
| `kit_gpu_server` | Compact AI compute server box with a large front fan, matte lavender and charcoal |
| `kit_storage_array` | Storage array cabinet with stacked drive bays, matte light grey, small status lights |
| `kit_ai_orb` | Small smart-speaker-like device with a soft glowing sphere on top, matte white |
| `kit_text_machine` | Friendly compact sorting machine with a short conveyor belt carrying paper cards, rounded, matte pastel |
| `kit_agent_robot` | Small friendly desk robot, rounded body, small screen face, matte white with one accent colour |
| `kit_tablet_stand` | Tablet on a slim floor stand, blank screen |
| `kit_phone_booth` | Acoustic office phone booth, felt panels, glass door, small desk inside |
| `kit_plant_large` | Large monstera plant in a matte ceramic pot |

---

## 9. Milestones (proof of concept first)

1. Style frame image (§8.1) → pick one.
2. Room images for **IT** and **Consulting** only (they carry the hero finding: data platform and dev cluster).
3. Asset kit v1: build the 36 reusable assets in §7 and review the contact sheet.
4. Import into the React scene, replace procedural desks in two rooms, check performance (target ≥ 50 fps on a normal laptop).
5. Only then: remaining rooms and assets. Keep the procedural version as fallback until the pitch.
