// The director turns a run's timeline into what the stage shows. It never invents anything:
// every change on the stage comes from one recorded event, and the feed highlights that event.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const tickKey = (e) => `${e.period}:${e.step ?? 'end'}`

// Seconds each event holds the stage at 1× (people's words get time to be read).
function weight(e) {
  switch (e.type) {
    case 'decision': return e.payload?.no_action || e.payload?.error ? 0.8 : 1.9
    case 'response_given':
    case 'message_sent': return 1.7
    case 'action_rejected': return 1.5
    case 'obstacle': return 1.3
    case 'capacity_changed': return 1.0
    case 'occurrence_cancelled': return 0.9
    case 'request_filed': return 1.3
    case 'request_decided':
    case 'request_endorsed':
    case 'request_endorsement_refused': return 1.0
    case 'queue_over_capacity': return 1.1
    case 'check_evaluated': return 1.0
    case 'record_corrected': return 0.45
    case 'many_missed': return 0.55
    case 'count_near_threshold': return 0.7
    case 'duty_planned': return 0.25
    case 'duty_recorded': return 0.14
    case 'queue_processed': return e.payload?.processed?.length ? 0.6 : 0.08
    case 'decision_awaiting': return e.payload?.offered?.length ? 0.4 : 0.05
    default: return 0.3
  }
}

export const BUBBLE_SECONDS = 2.6

/** starts[i]: when event i begins (1× seconds); a pause before each new step lets people walk. */
export function timing(events) {
  const starts = new Array(events.length)
  let t = 0
  let last = null
  for (let i = 0; i < events.length; i++) {
    const e = events[i]
    const k = tickKey(e)
    if (k !== last) { t += e.step == null ? 1.5 : last == null ? 0.4 : 0.85; last = k }
    starts[i] = t
    t += weight(e)
  }
  return { starts, total: t + 0.6 }
}

export function indexAt(starts, time) {
  let lo = 0
  let hi = starts.length
  while (lo < hi) { const mid = (lo + hi) >> 1; if (starts[mid] <= time) lo = mid + 1; else hi = mid }
  return lo // number of events that have begun
}

/** The stage's logical state after the first `count` events. */
export function deriveWorld(events, count, words) {
  const agents = {}
  for (const id of words.travellers) agents[id] = { zone: 'home', mark: null, slip: false, badge: null, bubble: null, mood: 'idle', count: null }
  for (const id of words.staff) agents[id] = { zone: 'post', mark: null, slip: false, badge: null, bubble: null, mood: 'idle' }
  const w = {
    period: 1, step: null, tick: null, phase: 'start',
    agents,
    hazards: [],
    duty: { cancelled: false, missedCount: 0 },
    desk: { capacity: null, capacityNote: null, pending: [], decided: [], over: false, held: [] },
    checks: {}, // person -> {passed, value, outcome}
    links: [],
    current: null,
    records: {}, // person -> {step -> met|missed}
  }
  const isTraveller = (id) => words.travellers.includes(id)
  const bubble = (id, kind, text, i) => { if (agents[id]) agents[id].bubble = { kind, text, i } }

  for (let i = 0; i < count && i < events.length; i++) {
    const e = events[i]
    const p = e.payload || {}
    const k = tickKey(e)
    if (k !== w.tick) {
      w.tick = k
      w.period = e.period
      w.step = e.step
      w.phase = e.step == null ? 'end' : 'step'
      w.hazards = []
      w.duty = { cancelled: false, missedCount: 0 }
      w.links = []
      w.desk.decided = []
      if (e.step == null) w.desk.over = false
      for (const a of Object.values(agents)) { a.mark = null; a.mood = a.badge === 'fail' ? 'sad' : 'idle'; a.refused = false }
      if (e.step == null) for (const id of words.travellers) { agents[id].zone = 'home'; agents[id].slip = false }
    }
    w.current = e
    const actor = e.actor
    switch (e.type) {
      case 'obstacle':
        w.hazards.push({ i, text: p.description, delay: p.delay, people: p.people || [] })
        for (const id of p.people || []) if (agents[id]) agents[id].mood = 'think'
        break
      case 'capacity_changed':
        w.desk.capacityNote = { from: e.state_change ? Object.values(e.state_change)[0]?.from : null, to: p.capacity, period: e.period, text: p.description }
        w.desk.capacity = p.capacity
        break
      case 'occurrence_cancelled':
        w.duty.cancelled = true
        break
      case 'decision': {
        const text = p.error ? 'No decision (the AI call failed)' : p.no_action ? 'Chose to do nothing.' : p.reason
        bubble(actor, 'think', text, i)
        if (agents[actor]) agents[actor].mood = 'think'
        break
      }
      case 'duty_planned':
        if (isTraveller(actor)) agents[actor].zone = p.plan === 'miss' ? 'home' : 'route'
        break
      case 'duty_recorded': {
        const who = p.person
        if (!agents[who]) break
        ;(w.records[who] ||= {})[e.step] = p.outcome
        agents[who].mark = p.outcome
        if (p.outcome === 'met') { agents[who].zone = 'duty'; agents[who].mood = 'happy' }
        else {
          const hit = p.obstacle || w.hazards.some((h) => h.people.includes(who))
          agents[who].zone = hit ? 'stuck' : 'home'
          agents[who].mood = 'sad'
          w.duty.missedCount += 1
        }
        break
      }
      case 'record_corrected': {
        const [key, ch] = Object.entries(e.state_change || {})[0] || []
        if (key) {
          const parts = key.split('.')
          const who = p.person || parts[2]
          const step = Number(parts[3])
          if (who && step) (w.records[who] ||= {})[step] = ch?.to
          bubble(actor, 'say', `Corrected ${who}'s record for ${step ? `#${step}` : 'a session'}: ${ch?.from ?? '—'} → ${ch?.to ?? '—'}`, i)
        }
        break
      }
      case 'action_rejected':
        bubble(actor, 'refused', p.detail || 'This action was refused.', i)
        if (agents[actor]) { agents[actor].mood = 'refused'; agents[actor].refused = true }
        break
      case 'request_filed': {
        const who = p.person || actor
        if (agents[who] && isTraveller(who)) { agents[who].zone = 'desk'; agents[who].slip = true }
        if (!w.desk.pending.includes(p.request_id)) w.desk.pending = [...w.desk.pending, p.request_id]
        bubble(who, 'say', p.reason ? `Filed ${p.request_id}: “${p.reason}”` : `Filed ${p.request_id}`, i)
        break
      }
      case 'request_endorsed':
      case 'request_endorsement_refused':
        bubble(actor, e.type === 'request_endorsed' ? 'say' : 'refused', p.reason || (e.type === 'request_endorsed' ? `Consent given for ${p.request_id}` : `Consent refused for ${p.request_id}`), i)
        if (p.person) w.links.push({ from: actor, to: p.person, i })
        break
      case 'request_decided':
        w.desk.pending = w.desk.pending.filter((r) => r !== p.request_id)
        w.desk.decided = [...w.desk.decided, { id: p.request_id, decision: p.decision }]
        for (const [id, a] of Object.entries(agents)) if (a.zone === 'desk' && a.slip && isTraveller(id)) a.mood = p.decision === 'approved' ? 'happy' : 'sad'
        if (p.reason && agents[actor] && words.isAI(actor)) bubble(actor, 'say', p.reason, i)
        break
      case 'queue_processed':
        if (p.capacity != null) w.desk.capacity = p.capacity
        if (Array.isArray(p.pending)) w.desk.pending = p.pending
        break
      case 'decision_awaiting':
        if (p.capacity != null) w.desk.capacity = p.capacity
        break
      case 'queue_over_capacity':
        w.desk.over = true
        w.desk.held = p.held || []
        break
      case 'response_given':
      case 'message_sent': {
        const to = p.to || p.student
        const text = p.advice || p.message || p.text || p.response || ''
        bubble(actor, 'say', text, i)
        if (to) w.links.push({ from: actor, to, i })
        break
      }
      case 'many_missed':
        break
      case 'count_near_threshold':
        if (agents[p.person]) agents[p.person].count = { value: p.value, threshold: p.threshold, i }
        break
      case 'check_evaluated': {
        const who = p.person
        const passed = !!p.passed
        // a ladder step (warning, guardian informed…) is a stage on the way, not a pass
        const ladder = p.ladder_steps != null
        const badge = ladder ? (p.outcome && !passed ? 'fail' : p.outcome || p.standing ? 'warn' : 'pass') : passed ? 'pass' : 'fail'
        w.checks[who] = { passed, badge, value: p.count?.value, threshold: p.threshold, outcome: p.outcome || p.standing, i }
        if (agents[who] && isTraveller(who)) {
          agents[who].zone = 'check'
          agents[who].badge = badge
          agents[who].mood = badge === 'pass' ? 'happy' : 'sad'
          agents[who].slip = false
        }
        break
      }
      default:
        break
    }
  }
  return w
}

/**
 * usePlayback: a clock over the timeline. Returns the number of events applied, the clock in
 * 1× seconds, and the controls. While a run is live, new events join the end and the clock
 * keeps going when it reaches them.
 */
export function usePlayback(events, { autoplay = true, initialSpeed = 2, startAtEnd = false } = {}) {
  const { starts, total } = useMemo(() => timing(events), [events])
  const [playing, setPlaying] = useState(autoplay && !startAtEnd)
  const [speed, setSpeed] = useState(initialSpeed)
  const [seekNonce, setSeekNonce] = useState(0)
  const timeRef = useRef(startAtEnd ? total : 0)
  const [time, setTime] = useState(timeRef.current)
  const totalRef = useRef(total)
  totalRef.current = total
  const startedAtEnd = useRef(startAtEnd)

  // jump to the end once if asked and events arrive after mount
  useEffect(() => {
    if (startedAtEnd.current && events.length) { timeRef.current = total; setTime(total); setSeekNonce((n) => n + 1); startedAtEnd.current = false }
  }, [events.length, total])

  useEffect(() => {
    if (!playing) return
    let raf
    let last = performance.now()
    let lastPush = 0
    const loop = (now) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      timeRef.current = Math.min(totalRef.current, timeRef.current + dt * speed)
      if (now - lastPush > 90) { setTime(timeRef.current); lastPush = now }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed])

  const count = indexAt(starts, time)
  const atEnd = time >= total - 0.001 || (count >= events.length && events.length > 0 && time >= starts[starts.length - 1])

  const seekTime = useCallback((t) => {
    timeRef.current = Math.max(0, Math.min(totalRef.current, t))
    setTime(timeRef.current)
    setSeekNonce((n) => n + 1)
  }, [])
  const seekIndex = useCallback((i) => {
    if (!events.length) return
    const j = Math.max(0, Math.min(events.length - 1, i))
    seekTime(starts[j] + 0.001)
  }, [events.length, starts, seekTime])
  const seekPeriod = useCallback((period) => {
    const j = events.findIndex((e) => e.period >= period)
    if (j >= 0) seekTime(Math.max(0, starts[j] - 0.3))
  }, [events, starts, seekTime])

  return {
    starts, total, time, count, playing, speed, atEnd, seekNonce,
    play: () => { if (atEnd && !events.length) return; if (time >= totalRef.current - 0.01) seekTime(0); setPlaying(true) },
    pause: () => setPlaying(false),
    toggle: () => setPlaying((p) => !p),
    restart: () => { seekTime(0); setPlaying(true) },
    toEnd: () => { seekTime(totalRef.current); setPlaying(false) },
    setSpeed,
    seekIndex,
    seekPeriod,
  }
}

/**
 * Where the clock stands: the current period and step, how far through the step the playback is
 * (frac), and a continuous position in periods for the time ruler.
 */
export function clockAt(events, starts, time, count, words) {
  if (!count || !events.length) return { period: null, step: null, frac: 0, position: 0, text: 'start of term' }
  const i = Math.min(count, events.length) - 1
  const e = events[i]
  const key = tickKey(e)
  let a = i
  while (a > 0 && tickKey(events[a - 1]) === key) a--
  let b = i + 1
  while (b < events.length && tickKey(events[b]) === key) b++
  const t0 = starts[a]
  const t1 = b < events.length ? starts[b] : (starts[events.length - 1] ?? t0) + 1.2
  const frac = Math.max(0, Math.min(1, (time - t0) / Math.max(0.001, t1 - t0)))
  const spp = words.cal.steps_per_period || 1
  const within = e.step == null ? spp - 0.2 + 0.2 * frac : words.stepInPeriod(e.step) - 1 + frac
  const position = e.period - 1 + Math.min(spp, within) / spp
  return { period: e.period, step: e.step, frac, position, text: words.where(e.period, e.step) }
}
