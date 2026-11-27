// Timeline events in plain words, in the template's terms (docs/USER_JOURNEY.md, S5 table).
import { useEffect, useMemo, useRef } from 'react'
import { Chip, cx } from '../ui/primitives.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { humanize } from '../lib/words.js'
import { AdaptedBadge } from './adaptation.jsx'

export const FILTERS = [
  { id: 'disruptions', label: 'Disruptions' },
  { id: 'decisions', label: 'AI decisions' },
  { id: 'refused', label: 'Refused' },
  { id: 'requests', label: 'Requests' },
  { id: 'records', label: 'Records' },
  { id: 'checks', label: 'Checks' },
]
export const DEFAULT_FILTERS = ['disruptions', 'decisions', 'refused', 'requests', 'checks']

const CHIP = {
  obstacle: 'disruptions', capacity_changed: 'disruptions', occurrence_cancelled: 'disruptions',
  decision: 'decisions', duty_planned: 'decisions', attribute_set: 'decisions', message_sent: 'decisions', response_given: 'decisions',
  action_rejected: 'refused',
  request_filed: 'requests', request_decided: 'requests', queue_processed: 'requests', queue_over_capacity: 'requests',
  decision_awaiting: 'requests', decision_not_made: 'requests', request_endorsed: 'requests', request_endorsement_refused: 'requests',
  duty_recorded: 'records', record_corrected: 'records',
  many_missed: 'checks', count_near_threshold: 'checks', check_evaluated: 'checks',
  // slice M7a/M5: the cost on the other side, and plans people stated for later
  obligation_missed: 'checks', obligation_lost: 'checks',
  intention_due: 'decisions', intention_resolved: 'decisions',
}
export const chipOf = (e) => {
  // routine queue ticks with nothing in them are records, not requests
  if (e.type === 'queue_processed' && !e.payload?.processed?.length && !e.payload?.pending?.length) return 'records'
  if (e.type === 'decision_awaiting' && !e.payload?.offered?.length && !e.payload?.held?.length) return 'records'
  return CHIP[e.type] || 'records'
}

const list = (a) => (a && a.length ? a.join(', ') : 'none')
const steps = (w, s) => (s && s.length ? `${w.step} ${s.join(', ')}` : '')

/** Who an event is about: the actor, or the person named in it. */
export function peopleOf(e) {
  const p = e.payload || {}
  const out = new Set()
  if (e.actor) out.add(e.actor)
  if (p.person) out.add(p.person)
  if (p.to) out.add(p.to)
  if (Array.isArray(p.people)) p.people.forEach((x) => out.add(x))
  return out
}

export function describe(e, w) {
  const p = e.payload || {}
  const who = (id) => humanize(id)
  switch (e.type) {
    case 'obstacle':
      return { tone: 'orange', icon: '⚠', title: `${p.description}${p.delay ? `: ${p.delay} min delay` : ''} for ${list(p.people)}` }
    case 'capacity_changed': {
      const ch = Object.values(e.state_change || {})[0]
      return { tone: 'orange', icon: '⚠', title: `${p.description}: capacity this ${w.period} ${ch?.from ?? '?'} → ${p.capacity}` }
    }
    case 'occurrence_cancelled':
      return { tone: 'orange', icon: '⊘', title: `${humanize(w.step)} ${e.step} cancelled${p.description && p.description.toLowerCase() !== `${w.step} cancelled` ? `: ${p.description}` : ''}` }
    case 'decision': {
      if (p.error) return { tone: 'muted', icon: '…', title: `${who(e.actor)}: no decision (the AI call failed)` }
      if (p.no_action) return { tone: 'muted', icon: '…', title: `${who(e.actor)} chose to do nothing`, quote: p.reason, sub: p.strategy }
      const acts = (p.proposals || []).map((x) => humanize(x.action)).join(', ')
      return { tone: 'blue', icon: '“', title: `${who(e.actor)} decided${acts ? `: ${acts}` : ''}`, quote: p.reason, sub: p.strategy ? `Strategy: ${p.strategy}` : null }
    }
    case 'action_rejected':
      // slice M4: a claimed cause that isn't hitting them is an AI mistake, said so plainly
      if (String(p.reason || '').startsWith('claim')) {
        return { tone: 'bad', icon: '✕', title: `${who(e.actor)}'s claimed cause refused (an AI mistake): ${p.detail || 'nothing like that is affecting them'}` }
      }
      return { tone: 'bad', icon: '✕', title: `${who(e.actor)}'s ${humanize(p.action)} refused: ${p.detail || 'not allowed'}` }
    case 'obligation_missed':
      return { tone: 'orange', icon: '⚖', title: `${who(p.person)} kept the rule and missed their ${p.obligation} (${p.missed} of ${p.limit} they can miss)` }
    case 'obligation_lost':
      return { tone: 'bad', icon: '⚖', title: `${who(p.person)} kept the rule past their limit of ${p.limit}: ${p.lost}` }
    case 'intention_due':
      return { small: true, tone: 'muted', icon: '·', title: `${who(p.person)} is reminded of what they planned: ${(p.intentions || []).map((x) => humanize(x.action)).join(', ')}` }
    case 'intention_resolved':
      return { small: true, tone: p.met ? 'ok' : 'muted', icon: p.met ? '✓' : '·', title: `${who(p.person)} ${p.met ? 'did' : "didn't do"} what they planned in ${w.step} ${p.stated_at}: ${humanize(p.action)}` }
    case 'duty_planned':
      return { small: true, tone: 'muted', icon: '·', title: `${who(e.actor)} plans to ${p.plan === 'miss' ? `be ${w.terms.duty_missed}` : humanize(p.action)}` }
    case 'attribute_set': {
      const ch = Object.values(e.state_change || {})[0]
      return { small: true, tone: 'muted', icon: '·', title: `${who(e.actor)}: ${humanize(p.attribute)} ${ch?.from ?? '—'} → ${ch?.to ?? '—'}` }
    }
    case 'request_filed':
      return { tone: 'blue', icon: '▤', title: `${who(p.person || e.actor)} filed ${w.terms.request} ${p.request_id} for ${steps(w, p.steps)}`, quote: p.reason, sub: p.awaiting_endorsement_by ? `Waiting for ${who(p.awaiting_endorsement_by)}'s consent` : (p.dropped?.length ? `Dropped: ${steps(w, p.dropped)}` : null) }
    case 'request_decided':
      return { tone: p.decision === 'approved' ? 'ok' : 'bad', icon: p.decision === 'approved' ? '✓' : '✕', title: `${p.request_id} ${p.decision} after ${p.waited_periods ?? 0} ${w.period}${p.waited_periods === 1 ? '' : 's'}`, quote: p.reason, sub: p.rejected_steps?.length ? `Approved ${steps(w, p.approved_steps) || 'none'}; rejected ${steps(w, p.rejected_steps)}` : null }
    case 'queue_processed':
      return { small: true, tone: 'muted', icon: '·', title: `${humanize(w.roleLabel(e.actor))} processed ${list(p.processed)} (capacity ${p.capacity}); waiting: ${list(p.pending)}` }
    case 'queue_over_capacity':
      return { tone: 'orange', icon: '⚠', title: `Over capacity: ${list(p.held)} wait${p.held?.length === 1 ? 's' : ''}` }
    case 'decision_awaiting':
      return { small: true, tone: 'muted', icon: '·', title: `${who(e.actor)} has ${p.offered?.length || 0} to decide (capacity ${p.capacity})${p.held?.length ? `; held: ${list(p.held)}` : ''}` }
    case 'decision_not_made':
      return { tone: 'orange', icon: '…', title: `${who(e.actor)} didn't decide ${list(p.offered || p.held)}` }
    case 'request_endorsed':
      return { tone: 'ok', icon: '✓', title: `${who(e.actor)} gave consent for ${p.request_id} (${who(p.person)})`, quote: p.reason }
    case 'request_endorsement_refused':
      return { tone: 'bad', icon: '✕', title: `${who(e.actor)} refused consent for ${p.request_id} (${who(p.person)})`, quote: p.reason }
    case 'duty_recorded':
      return { small: true, tone: p.outcome === 'met' ? 'ok' : 'bad', icon: p.outcome === 'met' ? '✓' : '✕', title: `${who(p.person)}: ${w.duty(p.outcome)}${p.obstacle ? ' (delayed)' : ''}` }
    case 'record_corrected': {
      const ch = Object.values(e.state_change || {})[0]
      const k = Object.keys(e.state_change || {})[0] || ''
      const step = k.split('.')[3]
      return { small: true, tone: 'muted', icon: '✎', title: `${who(e.actor)} corrected ${who(p.person)}'s ${w.step} ${step}: ${w.duty(ch?.from)} → ${w.duty(ch?.to)}` }
    }
    case 'many_missed':
      return { tone: 'orange', icon: '!', title: `${p.people?.length || 0} ${w.terms.duty_missed} in ${w.step} ${e.step}: ${list(p.people)}` }
    case 'count_near_threshold':
      return { tone: 'orange', icon: '!', title: `${who(p.person)} is at ${Number(p.value).toFixed(1)}${w.terms.count.includes('%') ? '%' : ''}, at the threshold (${p.threshold})` }
    case 'message_sent':
    case 'response_given':
      return { tone: 'blue', icon: '→', title: `${who(e.actor)} → ${who(p.to || p.student)}`, quote: p.advice || p.message || p.text || p.response }
    case 'check_evaluated': {
      const c = p.count || {}
      const ladder = p.ladder_steps != null
      const fig = c.kind === 'rate' ? `${c.met} / ${c.due} = ${c.value}%` : `${c.value} ${w.terms.count}`
      const outcome = ladder ? (p.outcome || (p.standing ? `still ${p.standing}` : 'no step')) : w.outcome(p.passed)
      const pass = ladder ? !p.outcome : p.passed
      return { tone: pass ? 'ok' : 'bad', icon: pass ? '✓' : '✕', title: `${w.template.checks?.find((x) => x.id === p.check)?.label || humanize(p.check)} for ${who(p.person)}, ${w.period} ${e.period}: ${fig} (needs ${p.comparison || ''} ${p.threshold}) → ${outcome}`, sub: p.pending_requests?.length ? `Still waiting: ${list(p.pending_requests)}` : null }
    }
    default:
      return { small: true, tone: 'muted', icon: '·', title: humanize(e.type) }
  }
}

const TONE = {
  orange: 'bg-orange-50 text-orange-700 border-orange-100',
  bad: 'bg-bad-50 text-bad border-transparent',
  ok: 'bg-ok-50 text-ok border-transparent',
  blue: 'bg-blue-50 text-blue-700 border-blue-100',
  muted: 'bg-mist text-ink-3 border-line',
  ink: 'bg-ink text-white border-ink',
}

export function EventRow({ e, w, current, onClick, adapted }) {
  const d = describe(e, w)
  const person = e.actor && (w.travellers.includes(e.actor) || w.staff.includes(e.actor)) ? e.actor : e.payload?.person
  return (
    <li data-current={current ? 'true' : undefined}>
      <button type="button" onClick={onClick}
        className={cx('w-full text-left flex gap-3 rounded-xl px-2.5 transition', d.small ? 'py-1' : 'py-2', current ? 'bg-white/90 shadow-[0_8px_24px_-16px_rgba(20,34,80,.4)] ring-1 ring-blue-200' : 'hover:bg-white/50')}>
        <span className={cx('mt-0.5 grid place-items-center shrink-0 rounded-full border font-semibold', d.small ? 'w-5 h-5 text-[10px]' : 'w-6 h-6 text-[11px]', TONE[d.tone])} aria-hidden>{d.icon}</span>
        <span className="min-w-0 flex-1">
          <span className={cx('block', d.small ? 'text-[12px] text-ink-3' : 'text-[13px] text-ink')}>
            {person && !d.small && <span className="inline-block align-[-3px] mr-1"><PersonAvatar colour={w.colour(person)} ai={w.isAI(person)} size={16} /></span>}
            {d.title}
            <AdaptedBadge kind={adapted} />
          </span>
          {d.quote && <span className={cx('block mt-1 text-[12.5px] text-ink-2 italic leading-snug', !current && 'line-clamp-2')}>“{d.quote}”</span>}
          {d.sub && current && <span className="block mt-0.5 text-[11.5px] text-ink-3">{d.sub}</span>}
        </span>
        <span className="font-mono text-[10px] text-ink-4 shrink-0 mt-1">{e.event_id}</span>
      </button>
    </li>
  )
}

/** The feed: events so far, grouped by period then step, newest last; follows while playing. */
export function EventFeed({ events, count, w, filters, setFilters, person, onPick, follow = true, className, adapted = {} }) {
  const shown = useMemo(() => {
    const upTo = events.slice(0, count)
    return upTo.filter((e) => filters.includes(chipOf(e)) && (!person || peopleOf(e).has(person)))
  }, [events, count, filters, person])
  const counts = useMemo(() => {
    const c = {}
    for (const e of events.slice(0, count)) { const k = chipOf(e); c[k] = (c[k] || 0) + 1 }
    return c
  }, [events, count])
  const box = useRef(null)
  const currentId = events[count - 1]?.event_id
  // keep the current event in view (while playing, after a seek, or at the end)
  useEffect(() => {
    if (!box.current) return
    const el = box.current.querySelector('[data-current="true"]')
    if (el) {
      const b = box.current.getBoundingClientRect()
      const r = el.getBoundingClientRect()
      if (r.top < b.top || r.bottom > b.bottom) box.current.scrollTop += r.bottom - b.bottom + (r.top < b.top ? r.top - r.bottom - 8 : 8)
    } else box.current.scrollTop = box.current.scrollHeight
  }, [currentId, shown.length, follow])

  const groups = []
  let last = null
  for (const e of shown) {
    const k = `${e.period}:${e.step ?? 'end'}`
    if (k !== last) { groups.push({ k, period: e.period, step: e.step, items: [] }); last = k }
    groups[groups.length - 1].items.push(e)
  }
  const toggle = (id) => setFilters(filters.includes(id) ? filters.filter((f) => f !== id) : [...filters, id])

  return (
    <div className={cx('flex flex-col min-h-0', className)}>
      <div className="flex flex-wrap gap-1.5 mb-3" role="group" aria-label="Show event types">
        {FILTERS.map((f) => <Chip key={f.id} active={filters.includes(f.id)} onClick={() => toggle(f.id)} count={counts[f.id] || 0}>{f.label}</Chip>)}
      </div>
      <div ref={box} className="thin-scroll overflow-y-auto min-h-0 flex-1 -mx-1 px-1" aria-live="off">
        {groups.length === 0 && <p className="text-[13px] text-ink-3 py-6 text-center">Nothing to show yet{person ? ` for ${humanize(person)}` : ''}. Press play, or turn on more event types.</p>}
        {groups.map((g) => (
          <section key={g.k} className="mb-2">
            <h4 className="sticky top-0 z-[1] bg-white/80 backdrop-blur py-1.5 px-2.5 rounded-lg text-[11.5px] font-semibold text-ink-2">{w.where(g.period, g.step)}</h4>
            <ul className="flex flex-col gap-0.5">
              {g.items.map((e) => <EventRow key={e.event_id} e={e} w={w} current={e.event_id === currentId} onClick={() => onPick?.(e)} adapted={adapted[e.event_id]} />)}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
