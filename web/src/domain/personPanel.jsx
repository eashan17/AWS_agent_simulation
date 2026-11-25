// The person panel (slice 20): everything about one person in a run, in one place. Read from the
// run's events, its blueprint and the adaptations route; no new data. Every item shows its event
// ID; clicking it moves the map to that moment (onJump).
import { useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Badge, Button, cx } from '../ui/primitives.jsx'
import { IconX } from '../ui/icons.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { describe } from './events.jsx'
import { EvidenceLabel } from './labels.jsx'
import { KIND_TEXT } from './adaptation.jsx'
import { cap, humanize, pct } from '../lib/words.js'

function Section({ title, count, children }) {
  return (
    <section className="py-4 border-t border-line first:border-0">
      <h4 className="eyebrow !text-[10.5px] mb-2.5">{title}{count != null ? ` · ${count}` : ''}</h4>
      {children}
    </section>
  )
}

function Jump({ id, onJump }) {
  if (!id) return null
  return onJump
    ? <button type="button" onClick={() => onJump(id)} className="font-mono text-[10.5px] text-blue-700 hover:underline shrink-0" title="Show this moment on the map" aria-label={`${id}: show this moment on the map`}>{id}</button>
    : <span className="font-mono text-[10.5px] text-ink-4 shrink-0">{id}</span>
}

/** Everything the panel shows, worked out once from the run's events. */
function usePersonFacts(id, events) {
  return useMemo(() => {
    const records = new Map() // `${duty}.${step}` -> {step, outcome, event_id, corrected}
    const requests = new Map()
    const decisions = []
    const refused = []
    let check = null
    for (const e of events) {
      const p = e.payload || {}
      for (const [key, ch] of Object.entries(e.state_change || {})) {
        const parts = key.split('.')
        if (parts.length === 4 && parts[0] === 'record' && parts[2] === id) {
          const k = `${parts[1]}.${parts[3]}`
          const prev = records.get(k)
          records.set(k, { step: Number(parts[3]), outcome: ch.to, event_id: e.event_id,
            corrected: e.type === 'record_corrected' ? { by: e.actor, from: ch.from } : prev?.corrected })
        }
      }
      if (e.type === 'request_filed' && (p.person || e.actor) === id) {
        requests.set(p.request_id, { id: p.request_id, steps: p.steps || [], reason: p.reason, filed: e, decided: null })
      }
      if (e.type === 'request_decided' && requests.has(p.request_id)) requests.get(p.request_id).decided = e
      if (e.type === 'decision' && e.actor === id) decisions.push(e)
      if (e.type === 'action_rejected' && e.actor === id) refused.push(e)
      if (e.type === 'check_evaluated' && p.person === id) check = e
    }
    return { records: [...records.values()].sort((a, b) => a.step - b.step), requests: [...requests.values()], decisions, refused, check }
  }, [id, events])
}

export function PersonPanel({ id, events, words, blueprint, adaptations, onClose, onJump }) {
  const closeRef = useRef(null)
  const f = usePersonFacts(id, events)
  useEffect(() => {
    closeRef.current?.focus()
    const on = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [id, onClose])

  const values = blueprint?.blueprint?.values || {}
  const profile = values.profiles?.[id]
  const attributes = (words.template.parameters || []).filter((p) => p.type === 'attribute' && values[p.name]?.[id] != null)
  const role = words.role(id)
  const ai = words.isAI(id)
  const c = f.check?.payload
  const ladder = c && c.ladder_steps != null
  const mine = (adaptations || []).filter((a) => a.person === id)
  const missed = f.records.filter((r) => r.outcome === 'missed').length

  // Rendered into <body>: the page's glass containers use backdrop-filter, which would make `fixed`
  // position the panel inside them instead of against the window.
  return createPortal(
    <>
      <div className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-[1px] lg:bg-transparent lg:backdrop-blur-0 lg:pointer-events-none" onClick={onClose} aria-hidden />
      <aside role="dialog" aria-modal="true" aria-label={`About ${words.name(id)}`}
        className="fixed z-50 inset-y-0 right-0 w-full sm:w-[440px] bg-[var(--color-canvas,#EEF1F6)]/95 backdrop-blur-xl border-l border-white shadow-[-20px_0_60px_-30px_rgba(20,34,80,.45)] flex flex-col">
        <header className="flex items-start gap-3 p-5 pb-4 border-b border-line">
          <PersonAvatar colour={words.colour(id)} ai={ai} size={44} mood={c && c.passed === false ? 'sad' : 'idle'} />
          <div className="min-w-0 flex-1">
            <h3 className="text-[17px] font-semibold">{words.name(id)}</h3>
            <p className="text-[12.5px] text-ink-3">{words.label(id)}</p>
            <div className="mt-1.5 flex gap-1.5 flex-wrap">
              <Badge>{role?.label || humanize(id)}</Badge>
              {ai ? <Badge tone="blue">AI person</Badge> : <Badge>run by rules</Badge>}
            </div>
          </div>
          <Button ref={closeRef} size="sm" onClick={onClose} aria-label="Close" icon={<IconX size={14} />}>Close</Button>
        </header>

        <div className="flex-1 overflow-y-auto thin-scroll px-5 pb-8">
          <Section title="Who they are">
            {profile?.description && <p className="text-[13px] text-ink-2">{profile.description}</p>}
            <div className="mt-2 grid gap-1 text-[12.5px]">
              {profile?.goals?.length > 0 && <div><span className="text-ink-3">Wants </span>{profile.goals.join(' · ')}</div>}
              {profile?.constraints?.length > 0 && <div><span className="text-ink-3">Limited by </span>{profile.constraints.join(' · ')}</div>}
              {attributes.map((p) => {
                const a = words.template.attributes?.find((x) => x.id === p.attribute)
                return <div key={p.name} className="font-mono text-[12px]">{a?.label || p.name}: <span className="font-semibold">{values[p.name][id]}</span> <span className="text-ink-3 font-sans">(at the start)</span></div>
              })}
              {!profile && !attributes.length && <span className="text-ink-3">{ai ? 'No profile in this blueprint.' : 'Run by the template\'s rules: no goals or choices of their own.'}</span>}
            </div>
          </Section>

          {c && (
            <Section title={cap(words.template.checks?.[0]?.label || 'Check')}>
              <div className="flex items-center gap-2 flex-wrap text-[13px]">
                <span className={cx('w-2 h-2 rounded-full', c.passed ? 'bg-ok' : 'bg-bad')} />
                {!ladder && <span className="tabular font-semibold">{c.count?.kind === 'tally' ? c.count?.value : pct(c.count?.value)}</span>}
                <span>{ladder ? (c.outcome || c.standing || 'no step') : words.outcome(c.passed)}</span>
                {!ladder && c.threshold != null && <span className="text-ink-3">needs {words.template.checks?.[0]?.comparison || '≥'} {c.threshold}</span>}
                <span className="text-ink-3">· {words.period} {f.check.period}</span>
                <EvidenceLabel label="calculated" />
                <Jump id={f.check.event_id} onJump={onJump} />
              </div>
            </Section>
          )}

          {f.records.length > 0 && (
            <Section title="Their record" count={`${missed} ${words.terms.missed_plural || 'missed'}`}>
              <ol className="flex flex-wrap gap-1" aria-label="Record per occurrence">
                {f.records.map((r) => (
                  <li key={r.event_id + r.step}>
                    <button type="button" onClick={() => onJump?.(r.event_id)} title={`${cap(words.step)} ${r.step}: ${words.duty(r.outcome)}${r.corrected ? ` (corrected by ${humanize(r.corrected.by)}, was ${words.duty(r.corrected.from)})` : ''} · ${r.event_id}`}
                      className={cx('w-7 h-7 rounded-md text-[10.5px] font-semibold tabular grid place-items-center border',
                        r.outcome === 'met' ? 'bg-ok-50 text-ok border-transparent' : 'bg-bad-50 text-bad border-transparent',
                        r.corrected && 'ring-2 ring-orange-400')}>
                      {r.step}
                    </button>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-[11.5px] text-ink-3">Green = {words.terms.duty_met}, red = {words.terms.duty_missed}, ringed = corrected. Each box is one {words.step}; click to see it on the map.</p>
            </Section>
          )}

          {f.requests.length > 0 && (
            <Section title={cap(words.terms.requests || 'requests')} count={f.requests.length}>
              <ul className="flex flex-col gap-2">
                {f.requests.map((r) => {
                  const d = r.decided?.payload
                  return (
                    <li key={r.id} className="rounded-xl bg-white/70 border border-white px-3 py-2 text-[12.5px]">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-semibold">{r.id}</span>
                        <span className="text-ink-2">for {words.step}{r.steps.length > 1 ? 's' : ''} {r.steps.join(', ')} · filed {words.where(r.filed.period, r.filed.step)}</span>
                        {d ? <Badge tone={d.decision === 'approved' ? 'ok' : d.decision === 'rejected' ? 'bad' : 'orange'} className="!h-5 !text-[11px]">{humanize(d.decision)}{d.waited_periods != null ? ` after ${d.waited_periods} ${words.period}${d.waited_periods === 1 ? '' : 's'}` : ''}</Badge>
                          : <Badge tone="orange" className="!h-5 !text-[11px]">never decided</Badge>}
                        <span className="ml-auto flex gap-2"><Jump id={r.filed.event_id} onJump={onJump} />{r.decided && <Jump id={r.decided.event_id} onJump={onJump} />}</span>
                      </div>
                      {r.reason && <p className="mt-1 italic text-ink-2">“{r.reason}”</p>}
                    </li>
                  )
                })}
              </ul>
            </Section>
          )}

          {mine.length > 0 && (
            <Section title="How they adapted" count={mine.length}>
              <ul className="flex flex-col gap-2">
                {mine.map((a) => (
                  <li key={a.event_id + a.kind} className="text-[12.5px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge tone={a.kind === 'value_changed' ? 'orange' : 'blue'} className="!h-5 !text-[11px]">{KIND_TEXT[a.kind]}</Badge>
                      <Jump id={a.event_id} onJump={onJump} />
                    </div>
                    <p className="mt-1">{a.kind === 'strategy_shift' ? <>“{a.from}” → <span className="italic">“{a.to}”</span></> : a.text}</p>
                    {a.effects?.map((x, i) => <p key={i} className="mt-1 text-ink-2">→ {x.text}</p>)}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {f.decisions.length > 0 && (
            <Section title="Every decision" count={f.decisions.length}>
              <ol className="flex flex-col gap-2.5">
                {f.decisions.map((e) => {
                  const d = describe(e, words)
                  return (
                    <li key={e.event_id} className="text-[12.5px]">
                      <div className="flex items-center gap-2">
                        <span className="text-ink-3">{words.where(e.period, e.step)}</span>
                        <span className="ml-auto"><Jump id={e.event_id} onJump={onJump} /></span>
                      </div>
                      <p className="mt-0.5">{d.title}</p>
                      {e.payload?.reason && <p className="mt-0.5 italic text-ink-2">“{e.payload.reason}”</p>}
                      {e.payload?.strategy && <p className="mt-0.5 text-ink-3">Strategy: {e.payload.strategy}</p>}
                    </li>
                  )
                })}
              </ol>
              <p className="mt-2 text-[11.5px] text-ink-3"><EvidenceLabel label="AI interpretation" className="!h-5 mr-1" /> Their reasons and strategies are their own words, not facts.</p>
            </Section>
          )}

          {f.refused.length > 0 && (
            <Section title="Refused by the rules" count={f.refused.length}>
              <ul className="flex flex-col gap-1.5">
                {f.refused.map((e) => (
                  <li key={e.event_id} className="flex items-start gap-2 text-[12.5px]">
                    <span className="text-bad">✕</span>
                    <span className="flex-1">{humanize(e.payload?.action)}: {e.payload?.detail || humanize(e.payload?.reason)}</span>
                    <Jump id={e.event_id} onJump={onJump} />
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </aside>
    </>,
    document.body,
  )
}
