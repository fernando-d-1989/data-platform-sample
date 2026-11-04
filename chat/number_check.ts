/**
 * No figure in a chat answer may come from nowhere: every number must appear in
 * what the model had in front of it (a tool result, the question, the date).
 *
 * It compares the number, not the text: "1,234" and "1234" are the same figure.
 * It does not accept a different rounding: the model copies, it doesn't calculate.
 *
 * Limit: this proves the number came from somewhere, not that the sentence uses
 * it correctly. That part is what the exam measures.
 */
const NUMBER = /\d+(?:[.,]\d+)*/g

/** Every reasonable reading of a written number. "1,234" could be English or Spanish. */
export function readingsOf(token: string): number[] {
  const t = token.trim()
  const out = new Set<number>()
  const add = (s: string) => {
    const n = Number(s)
    if (Number.isFinite(n)) out.add(n)
  }
  if (/^\d{1,3}(?:\.\d{3})+(?:,\d+)?$/.test(t)) add(t.replace(/\./g, '').replace(',', '.'))
  if (/^\d+,\d+$/.test(t)) add(t.replace(',', '.'))
  if (/^\d{1,3}(?:,\d{3})+(?:\.\d+)?$/.test(t)) add(t.replace(/,/g, ''))
  if (/^\d+(?:\.\d+)?$/.test(t)) add(t)
  return [...out]
}

const key = (n: number) => n.toFixed(6)

function numbersIn(text: string): { token: string; readings: number[] }[] {
  return [...text.matchAll(NUMBER)]
    .map((m) => ({ token: m[0], readings: readingsOf(m[0]) }))
    .filter((x) => x.readings.length > 0)
}

/** The figures in `answer` found in none of `sources`. Empty means every figure is backed. */
export function unsupportedFigures(answer: string, sources: readonly string[]): string[] {
  const known = new Set<string>()
  for (const s of sources) for (const { readings } of numbersIn(s)) for (const n of readings) known.add(key(n))
  const loose: string[] = []
  for (const { token, readings } of numbersIn(answer)) {
    if (readings.some((n) => known.has(key(n)))) continue
    if (!loose.includes(token)) loose.push(token)
  }
  return loose
}
