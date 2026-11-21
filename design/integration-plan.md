# Gemello digitale: integrazione degli asset e piano delle funzioni

Stato al 21.11, sera. Avvio: `cd web && npm install && npm run dev`.
La scena usa ora i modelli di Blender (`web/public/models/`). Gli oggetti 3D li genera `design/blender/`, i dati per oggetto `web/scripts/items_mock.py`.

---

## 1. Come è fatto

```
design/blender/*.py ──► web/public/models/
                         ├─ env_office_v1.glb     edificio + arredi statici (1 modello)
                         ├─ env_islands_v1.glb    3 isole con «slot_*» per i server; la nuvola «UE mista» si toglie e diventa la forma delle nuvole di CO₂
                         ├─ kit_*_v1.glb          36 oggetti riusabili (scrivania, rack, robot…)
                         └─ layout.json           440 oggetti interattivi: id, asset, posizione, stanza

backend (output/*.json) ──► web/public/data/
                         ├─ summary / entities / measures / limits / findings / quality   (come prima)
                         └─ items.json            NUOVO: dati rapidi per oggetto (report, licenze, SaaS, AI, agenti)

web/src/data/twin.ts     collega oggetto della scena ↔ entità ↔ misure e calcola lo «stato visivo»
web/src/scene/twin/      Twin (composizione), KitInstances (instancing), Environment (GLB statici), colors
web/src/ui/              Nav (fasi), SummaryPill (target), ModePanel (pannello sinistro), Detail (scheda destra), Overlay (viste, legenda, avvisi, tour)
```

**Regola d'oro:** il 3D non contiene numeri. Ogni oggetto ha un **id stabile** (`layout.json`), e lo stato (colore di schermi e LED, visibilità, posizione) si calcola dai JSON a ogni cambio di misure. Quando arrivano i dati veri, la scena cambia da sola.

### Collegamento oggetto → dati (in quest'ordine)
1. `entities.json`: entità con lo **stesso id** (es. `dp-prod`, `gpu-ml`, `vm-test`).
2. `entities[].scene_ids`: alias (es. `storage-ch` → `st-proj`, `dp-storage`, `st-archive`).
3. `items.json[].entity_id`: report → `pbi-kap`, SaaS → `saas`, licenze → `ai-subs`, app AI e agenti → `ai-api`.
4. Postazioni `seat:<reparto>:NN` → `m365:<reparto>` in `items.json`. Licenze `lic:<prodotto>:<reparto>:NN` → gruppo `lic:<prodotto>:<reparto>`.

**Per il backend:** basta produrre `entities.json` con gli id di `mapping_departments_tools.csv` (resource_id) e, se possibile, `items.json` con lo schema di `ItemInfo` in `web/src/data/types.ts`. Più le entità sono fini (una per resource_id), meno alias servono.

---

## 2. Interazioni (già implementate)

| Azione | Risultato |
|---|---|
| Passare sopra un oggetto | tooltip con nome + frase chiave (es. «1 di 12 posti attivi») |
| Clic su un oggetto | anello verde, la camera vola sull'oggetto, scheda a destra con stato, numeri, scoperte, limiti, misure (con interruttore) e «Come è calcolato» |
| Clic su pavimento o etichetta di una stanza | la camera inquadra la stanza; scheda con FTE, postazioni, posti AI, report, contratti e tutte le risorse del reparto |
| Clic su un'isola o sulla sua etichetta | scheda della sede: rete kg/kWh (intervallo + fonte), cosa gira lì, prima/dopo |
| Briciole di pane nella scheda | Basilea › Reparto / Sede |
| Viste in basso a sinistra | Tutto · Ufficio · Data center |
| Mouse | trascina = ruota, rotella = zoom verso il cursore, tasto destro = sposta |
| Barra in alto | 4 fasi (Connetti, Scopri, Decidi, Limiti), metrica CO₂ / CHF / kWh, Tour, download dei 2 CSV |
| Pillola dei target | CO₂ e costi vs target, budget; il pulsante verde applica o azzera il pacchetto consigliato |
| URL per test e demo | `?pkg` · `?mode=find` · `?sel=dp-prod` · `?sel=room:it` · `?sel=loc:zurich` · `?sel=handover:queue` · `?tour=0` |

### Stati visivi (`web/src/scene/twin/colors.ts`)
| Stato | Schermo / LED | Quando |
|---|---|---|
| in uso | verde menta | posto attivo, risorsa normale |
| spreco | ambra (lampeggia sulle risorse) | licenza senza accessi, report quasi mai aperto, entità con tag `waste` |
| ridotto / spento | verde chiaro / grafite | una misura attiva la riduce o la spegne; ventole e nastri rallentano |
| tolto | sparisce con animazione | server dismesso (M4), licenze inattive disdette (M6) |
| spostato | vola ad arco nella nuova isola | dp-dev da Francoforte a Zurigo (M1, slot `slot_dp-dev_m1`) |
| protetto | blu-grigio | tag `locked`, finestre protette |
| decide una persona | azzurro | tag `human`, coda di approvazione con misure in attesa |

Pavimenti: più caldi = più peso del reparto sulla metrica scelta. Nuvole grigie sopra le isole (la nuvola modellata in Blender): grandezza ∝ CO₂ della sede. AI e SaaS («UE, sede non indicata») non hanno un'isola: non sono un luogo in più ma un mix non specificato; restano nei totali e negli oggetti in ufficio. Cavi: dalla console del reparto all'oggetto sull'isola; colore = intensità della rete, spessore = valore sulla metrica.

---

## 3. Funzioni obbligatorie: dove sono

| Fase del caso | Nel prototipo |
|---|---|
| **Connect** | Fase «Connetti»: totali, ripartizione per reparto e per sede (cliccabili), elenco della pulizia dati da `quality.json` |
| **Find** | Fase «Scopri»: 5 driver per la metrica scelta, scoperte con prova e fonte, badge sulle risorse, schermi ambra per licenze, SaaS e report |
| **Decide** | Fase «Decidi»: interruttori delle misure, pacchetto consigliato, budget; la scena cambia (vedi stati); misure bloccate barrate con motivo |
| **Know the limits** | Fase «Limiti»: finestre, blocchi, persone, contraddizioni; badge nel plastico; calendari a muro (`window:*`); coda di approvazione (B5) sulla scrivania in Management |
| **Ogni numero si apre** | «🧮 Come è calcolato» in ogni scheda (campo `calc`) |
| **Export CSV** | pulsante ⬇ in alto: usa `public/data/export/*.csv` del backend se c'è, altrimenti li genera dai JSON |
| **Tour (B10)** | 6 passi, frecce ← →, Esc |

---

## 4. Bonus e proposte: cosa manca e come farlo con questi asset

Ogni voce: **dato** (file + campi) → **scena** → **UI** → stima.

### A2 · Previsione 2026 → 2030 (`forecast.json`)
- **Dato:** `[{year, scenario: 'base'|'package', co2_kg: Range, cost_chf: Range}]` + crescita per entità (`growth_per_year`).
- **Scena:** cursore dell'anno → `representedCount` cresce: si aggiungono istanze di `server_rack_42u` sugli stessi slot (offset di 0.9 m). Le nuvole crescono.
- **UI:** slider sotto la pillola dei target + grafico a ventaglio (SVG semplice, 2 bande).
- **Stima:** 2.5 h.

### A1 · Assistente in chat (`/api/ask` o risposte preparate)
- **Dato:** risposta `{text, entity_ids[], calc?, sources[]}`.
- **Scena:** `select(sceneIdFor(entity_ids[0]))`, quindi la camera vola già da sola.
- **UI:** quinta scheda «Chiedi» nella barra (stile ricerca a pillola di Airbnb) + pannello con la risposta e le fonti.
- **Stima:** 3 h di frontend. Le 3 domande di `example_questions.md` vanno preparate come casi di test.

### A3 · Interruttore market-based
- **Dato:** `locations[].grid_market_kg_per_kwh` + `summary.baseline_market`.
- **Scena:** il colore dei cavi e delle isole usa il fattore market; un'etichetta «certificato» sulle isole.
- **UI:** interruttore «Location / Market» nella pillola CO₂. La pillola mostra sempre la location-based come obbligatoria.
- **Stima:** 1 h.

### B2 · Mix svizzero (produzione / consumo)
- **Dato:** già presente: `locations.CH.grid_alt_kg_per_kwh`. Serve che il backend esporti anche la baseline e i risparmi con il mix alternativo (`summary.alt`), per non ricalcolare nel frontend.
- **Scena:** isola di Zurigo e cavi CH cambiano colore; nuvola di Zurigo si riduce.
- **UI:** interruttore nella scheda della sede Zurigo + nella fase Connetti.
- **Stima:** 1 h.

### A5 · Carichi nelle ore pulite (`jobs.json` + intensità oraria)
- **Dato:** `[{job, entity_id, start, duration_h, flexible: bool, window?}]` + `hourly_intensity[24]` per sede.
- **Scena:** nessun asset nuovo; il calendario a muro `window:nightly-processing` diventa cliccabile come «linea del tempo».
- **UI:** striscia di 24 h nella scheda di dp-prod: blocchi colorati, quelli flessibili scivolano nelle ore verdi, quelli fissi con 🔒.
- **Stima:** 3 h.

### A6 · Pipeline di build
- **Dato:** `ci.json`: `{runs, runs_without_commit, by_night[]}` (da `extra/ci_pipeline_runs.jsonl`).
- **Scena:** riusare `text_machine` come «nastro dei build» sull'isola di Dublino (slot `cicd`): i pacchi vuoti sono build senza commit; con M8 il nastro rallenta (già collegato ad `activity`).
- **UI:** scheda di `cicd` con barre notte / giorno.
- **Stima:** 1 h.

### A4 · Clustering
- **Dato:** `clusters.json`: `[{entity_id | item_id, cluster, outlier: bool}]`.
- **Scena:** modalità «gruppi»: `colors.accent` delle istanze = colore del cluster, e gli outlier lampeggiano. Basta passare un'altra mappa colori a `KitInstances`.
- **UI:** legenda dei gruppi al posto di quella degli stati.
- **Stima:** 2 h.

### B1 · Pacchetto robusto (Monte Carlo)
- **Dato:** `montecarlo.json`: `{runs, co2_pct[], cost_pct[], p_target}`.
- **UI:** nella fase Decidi, istogramma piccolo + frase grande «target raggiunto nel X% degli scenari» (è il «rating display» di Airbnb: 64 px, l'unico numero gigante).
- **Stima:** 1.5 h.

### B4 · Calendario dei risparmi
- **Dato:** già presente: `measures[].start_month`; aggiungere `contract_end` per le licenze.
- **UI:** linea dei 12 mesi sotto la lista delle misure, con risparmio cumulato.
- **Stima:** 1.5 h.

### B11 · Giorno e notte
- **Dato:** `timeseries.json` orario o giornaliero per dp-prod / dp-dev / gpu-ml (runtime_h, active_h).
- **Scena:** `directionalLight` e `hemisphereLight` animate, i LED dei rack seguono acceso / attivo, gli schermi delle postazioni si spengono di notte.
- **UI:** slider 0–24 h sotto la scena.
- **Stima:** 3 h. Effetto forte, ma non obbligatorio.

### Intake animato (Connect)
- **Scena:** 28 icone di file (sprite HTML) che volano dal bordo verso la «console» `saas-m365` e le isole, poi i contatori di `quality.json` salgono.
- **Stima:** 2 h.

### B12 · Versione 2D di riserva
- **UI:** se WebGL manca, `App` mostra solo `ModePanel` + `Detail` a tutta larghezza (sono già indipendenti dalla scena).
- **Stima:** 1 h.

---

## 5. Ordine consigliato (tempo rimasto fino a domenica 08:30)

1. Collegare i **JSON veri** del backend (1 h): controllare che gli id coincidano con `layout.json` (vedi §1).
2. **B2 + A3** (2 h): piccoli, molto richiesti nella valutazione.
3. **B1** Monte Carlo (1.5 h): il numero «X% degli scenari» è forte nel pitch.
4. **A6** con il nastro su Dublino (1 h) e **A2** previsione (2.5 h).
5. Se resta tempo: **A1** chat, **B11** giorno e notte, intake animato.

## 6. Controlli prima del pitch
- `npm run build && npm run preview` su un portatile normale: target ≥ 50 fps (misurato qui: 60 fps a densità 2×).
- Provare tutti i parametri URL del §2. Il tour è il piano B se il mouse fa i capricci.
- La demo funziona offline: font incluso nel bundle (`@fontsource-variable/inter`), nessuna risorsa da CDN.
