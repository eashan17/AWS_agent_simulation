// The template's own words. No screen hard-codes "attendance", "student" or "week":
// everything is read from GET /api/templates/{id} (terms, calendar, people, roles).

export const humanize = (s) => (s == null ? '' : String(s).replace(/_/g, ' '))
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '')

const FALLBACK = {
  terms: { period: 'period', step: 'step', duty_met: 'met', duty_missed: 'missed', request: 'request', requests: 'requests',
    count: 'count', check_passed: 'passed', check_failed: 'failed', missed_plural: 'misses' },
  calendar: { periods: 10, steps_per_period: 1, period_label: 'period', step_label: 'step' },
  people: [], roles: [], parameters: [], checks: [],
}

/** The most common AI role is the population that travels on the stage (students, residents). */
export function travellerRole(t) {
  const counts = {}
  for (const p of t.people || []) counts[p.role] = (counts[p.role] || 0) + 1
  const llmRoles = new Set((t.roles || []).filter((r) => r.llm).map((r) => r.id))
  let best = null
  for (const [role, n] of Object.entries(counts)) if (llmRoles.has(role) && (!best || n > counts[best])) best = role
  return best
}

export function makeWords(template) {
  const t = template || FALLBACK
  const terms = { ...FALLBACK.terms, ...(t.terms || {}) }
  const cal = { ...FALLBACK.calendar, ...(t.calendar || {}) }
  const people = t.people || []
  const roles = t.roles || []
  const roleById = Object.fromEntries(roles.map((r) => [r.id, r]))
  const personById = Object.fromEntries(people.map((p) => [p.id, p]))
  const traveller = travellerRole(t)
  const travellers = people.filter((p) => p.role === traveller).map((p) => p.id)
  const staff = people.filter((p) => p.role !== traveller).map((p) => p.id)

  const colour = {}
  travellers.forEach((id, i) => { colour[id] = `var(--p${(i % 8) + 1})` })
  staff.forEach((id, i) => { colour[id] = `var(--staff-${(i % 3) + 1})` })

  const stepInPeriod = (step) => (step == null ? null : ((step - 1) % cal.steps_per_period) + 1)

  return {
    template: t,
    terms,
    cal,
    periods: cal.periods,
    period: cal.period_label || terms.period,
    step: cal.step_label || terms.step,
    traveller,
    travellers,
    staff,
    people,
    roles,
    colour: (id) => colour[id] || 'var(--staff-2)',
    role: (personId) => roleById[personById[personId]?.role],
    roleLabel: (personId) => roleById[personById[personId]?.role]?.label || cap(humanize(personId)),
    isAI: (personId) => !!roleById[personById[personId]?.role]?.llm,
    label: (id) => personById[id]?.label || humanize(id),
    /** "working" → "working · has fixed work hours" */
    who: (id) => (personById[id] ? `${humanize(id)} · ${personById[id].label}` : humanize(id)),
    name: (id) => humanize(id),
    /** term-wide step → "week 5 · session 9"; no step → "week 5 · end of week" */
    where: (period, step) => {
      const p = `${cal.period_label} ${period}`
      if (step == null) return `${p} · end of ${cal.period_label}`
      return `${p} · ${cal.step_label} ${step}`
    },
    /** a blueprint disruption's within-period steps → "session 1 of the week" */
    withinPeriod: (steps) => {
      if (!steps || !steps.length) return `the whole ${cal.period_label}`
      const list = steps.join(' and ')
      return `${cal.step_label}${steps.length > 1 ? 's' : ''} ${list} of the ${cal.period_label}`
    },
    stepInPeriod,
    outcome: (passed) => (passed ? terms.check_passed : terms.check_failed),
    duty: (outcome) => (outcome === 'met' ? terms.duty_met : outcome === 'missed' ? terms.duty_missed : humanize(outcome)),
    param: (name) => (t.parameters || []).find((p) => p.name === name),
  }
}

export function formatValue(v, param) {
  if (v === true) return 'yes'
  if (v === false) return 'no'
  if (v == null) return '—'
  if (typeof v === 'number') {
    if (param?.name?.endsWith('_pct')) return `${v}%`
    return String(v)
  }
  if (typeof v === 'string') return param?.type === 'choice' ? humanize(v) : v
  return JSON.stringify(v)
}

export function pct(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Number(v).toFixed(1).replace(/\.0$/, '')}%`
}

export function duration(a, b) {
  if (!a || !b) return null
  const s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}
