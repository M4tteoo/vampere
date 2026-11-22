/** Verbi mostrati a rotazione mentre l'assistente prepara la risposta. Modifica pure la lista: basta una parola per riga. */
export const SPINNER_VERBS = [
  'Thinking',
  'Altycaing',
  'Kilowatting',
  'Counting Co2 Atoms',
  'Chasing idle servers',
  'Crunching the francs',
  'Sniffing out waste',
  'Pietroing',
  'Matteoing',
  'Sebaing',
  'Ashleing',
  'Hunting unused seats',
  'Sharpening the fangs',
  'Dimming the lights',
  'Spilling the tea',
  'feeding the bats',
  'feeding the bats',
  'Sprintding to Basel',
  'abandoning italy for hacking'
]

/** Intervallo di rotazione in millisecondi. */
export const SPINNER_INTERVAL_MS = 2200

export const randomVerb = (except?: string) => {
  const pool = SPINNER_VERBS.filter((v) => v !== except)
  return pool[Math.floor(Math.random() * pool.length)] ?? 'Thinking'
}
