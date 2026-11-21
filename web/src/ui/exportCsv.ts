import type { Dataset } from '../data/types'

/** Scarica i due CSV di consegna. Se il backend li ha già prodotti (public/data/export/), usa quelli;
 *  altrimenti li genera dai JSON caricati (stessi numeri della demo). */
export async function exportCsvs(data: Dataset, active: string[]) {
  for (const name of ['template_measures_package', 'template_baseline_and_assumptions']) {
    const res = await fetch(`${import.meta.env.BASE_URL}data/export/${name}.csv`).catch(() => null)
    const ready = res?.ok && !(res.headers.get('content-type') ?? '').includes('html')
    const text = ready ? await res!.text() : name.includes('measures') ? measuresCsv(data, active) : baselineCsv(data)
    download(`${name}.csv`, text)
  }
}

const q = (v: unknown) => {
  const s = v === undefined || v === null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function measuresCsv(data: Dataset, active: string[]) {
  const head = [
    'measure_id', 'description', 'resource_or_source', 'change', 'effort_person_days', 'savings_cost_chf_per_year',
    'savings_energy_kwh_per_year', 'savings_co2_kg_location_based', 'savings_co2_kg_market_based', 'risks_and_exceptions',
    'assumptions_and_sources',
  ]
  const chosen = data.measures.filter((m) => (active.length ? active.includes(m.id) : m.recommended) && m.status !== 'blocked')
  const rows = chosen.map((m) => [
    m.id, m.title, m.effects.map((e) => e.entity_id).join(' '), m.description, m.effort_days, Math.round(m.savings.cost_chf),
    Math.round(m.savings.kwh), Math.round(m.savings.co2_kg), '', m.reason ?? '', [m.calc?.formula, ...m.sources].filter(Boolean).join(' · '),
  ])
  return [head, ...rows].map((r) => r.map(q).join(',')).join('\n') + '\n'
}

function baselineCsv(data: Dataset) {
  const s = data.summary
  const loc = (id: string) => s.locations.find((l) => l.id === id)
  const rows: unknown[][] = [
    ['parameter', 'must_or_bonus', 'value_low', 'value_mid', 'value_high', 'unit', 'source', 'calculation_or_assumption'],
    ['total_cost_baseline_year_chf', 'Must', '', s.baseline.cost_chf, '', 'CHF per year', 'cloud invoices + SaaS + AI', s.baseline_period],
    ['total_energy_baseline_year_kwh', 'Must', s.baseline_range?.kwh.low, s.baseline.kwh, s.baseline_range?.kwh.high, 'kWh per year', '', ''],
    ['total_co2_location_based_baseline_year_kg', 'Must', s.baseline_range?.co2_kg.low, s.baseline.co2_kg, s.baseline_range?.co2_kg.high, 'kg CO2 per year', '', ''],
    ...(['CH', 'DE', 'IE'] as const).map((id) => {
      const l = loc(id)
      const name = { CH: 'switzerland', DE: 'germany', IE: 'ireland' }[id]
      return [`grid_mix_location_based_${name}`, 'Must', l?.grid_kg_per_kwh.low, l?.grid_kg_per_kwh.mid, l?.grid_kg_per_kwh.high, 'kg CO2 per kWh', l?.source, '']
    }),
  ]
  return rows.map((r) => r.map(q).join(',')).join('\n') + '\n'
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
