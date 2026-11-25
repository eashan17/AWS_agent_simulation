// People: the strip beside the stage and the cards in blueprint review.
import { useMemo } from 'react'
import { Badge, cx } from '../ui/primitives.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { pct } from '../lib/words.js'

/** Latest facts per person from the events so far (counts, check results, decisions, last reason). */
export function usePeopleFacts(events, count, words) {
  return useMemo(() => {
    const f = {}
    const get = (id) => (f[id] ||= { decisions: 0, refused: 0, reason: null, count: null, check: null })
    for (const e of events.slice(0, count)) {
      const p = e.payload || {}
      if (e.type === 'decision') { const x = get(e.actor); x.decisions += 1; if (p.reason) x.reason = p.reason }
      if (e.type === 'action_rejected') get(e.actor).refused += 1
      if (e.type === 'count_near_threshold') get(p.person).count = p.value
      if (e.type === 'check_evaluated') {
        const x = get(p.person)
        x.count = p.count?.value
        const ladder = p.ladder_steps != null
        x.check = { passed: ladder ? !p.outcome : p.passed, value: p.count?.value, threshold: p.threshold, outcome: ladder ? (p.outcome || p.standing || 'no step') : words.outcome(p.passed), period: e.period, kind: p.count?.kind }
      }
    }
    return f
  }, [events, count, words])
}

export function PeopleStrip({ words, facts, selected, onSelect, decisionsByAgent }) {
  const ids = [...words.travellers, ...words.staff.filter((id) => words.isAI(id))]
  return (
    <ul className="flex flex-col gap-1.5">
      {ids.map((id) => {
        const x = facts[id] || {}
        const isSel = selected === id
        const decisions = decisionsByAgent?.[id] ?? x.decisions
        return (
          <li key={id}>
            <button type="button" onClick={() => onSelect(isSel ? null : id)} aria-pressed={isSel}
              className={cx('w-full text-left flex gap-3 items-start rounded-2xl px-3 py-2.5 border transition',
                isSel ? 'bg-white border-blue-200 shadow-[var(--shadow-glass)]' : 'bg-white/50 border-white hover:bg-white')}>
              <PersonAvatar colour={words.colour(id)} ai={words.isAI(id)} size={34} mood={x.check && !x.check.passed ? 'sad' : 'idle'} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13.5px] font-medium">{words.name(id)}</span>
                  {x.check && <Badge tone={x.check.passed ? 'ok' : 'bad'} className="!h-5 !text-[11px]">{x.check.passed ? '✓' : '✕'} {x.check.outcome}</Badge>}
                  {!x.check && x.count != null && <Badge tone="orange" className="!h-5 !text-[11px]">{x.check?.kind === 'tally' ? x.count : pct(x.count)}</Badge>}
                </span>
                <span className="block text-[11.5px] text-ink-3 truncate">{words.label(id)}</span>
                <span className="block text-[11.5px] text-ink-3 mt-0.5 font-mono">{decisions || 0} decision{decisions === 1 ? '' : 's'}{x.refused ? ` · ${x.refused} refused` : ''}</span>
                {x.reason && <span className="block mt-1 text-[12px] text-ink-2 italic line-clamp-2">“{x.reason}”</span>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function PersonCard({ id, words, profile, slack, slackLabel }) {
  return (
    <article className="rounded-2xl bg-white/70 border border-white p-4 flex gap-3">
      <PersonAvatar colour={words.colour(id)} size={44} />
      <div className="min-w-0 flex-1">
        <h4 className="text-[14px] font-semibold"><span>{words.name(id)}</span><span className="text-ink-3 font-normal">: {words.label(id)}</span></h4>
        {profile?.description && <p className="text-[12.5px] text-ink-2 mt-0.5">{profile.description}</p>}
        <div className="mt-2 grid gap-1 text-[12px]">
          {profile?.goals?.length > 0 && <div><span className="text-ink-3">Wants </span>{profile.goals.join(' · ')}</div>}
          {profile?.constraints?.length > 0 && <div><span className="text-ink-3">Limited by </span>{profile.constraints.join(' · ')}</div>}
          {slack != null && <div className="font-mono text-[11.5px] text-ink-2 mt-1">{slackLabel}: <span className="text-ink font-semibold">{slack}</span></div>}
        </div>
      </div>
    </article>
  )
}
