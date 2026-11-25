// Blueprint values, grouped by their parameter kind, each with its fact / assumption badge.
import { FactBadge } from './labels.jsx'
import { cx } from '../ui/primitives.jsx'
import { formatValue, humanize, cap } from '../lib/words.js'

const allLabels = (bp) => [
  ...(bp.blueprint?.facts || []).map((x) => ({ ...x, kind: 'fact' })),
  ...(bp.blueprint?.assumptions || []).map((x) => ({ ...x, kind: 'assumption' })),
]

/** The label for a value: one whose field is the value's name, else one whose field is its section. */
export function labelFor(bp, name, section) {
  const all = allLabels(bp)
  return all.find((x) => x.field === name) || all.find((x) => x.field === section) || null
}

/** Every label written for a whole section (field `policy`, `environment` or `people`), facts first. */
export function sectionLabels(bp, section) {
  return allLabels(bp).filter((x) => x.field === section)
}

/** The fact / assumption lines for a section or a value, in the same words as ParamRow. */
export function LabelLines({ labels, className }) {
  if (!labels?.length) return null
  return (
    <ul className={cx('flex flex-col gap-1', className)}>
      {labels.map((l, i) => (
        <li key={i} className={cx('text-[12.5px]', l.kind === 'fact' ? 'text-blue-700' : 'text-orange-700')}>
          {l.kind === 'fact' ? 'From your text: ' : 'AI assumption: '}{l.statement}
        </li>
      ))}
    </ul>
  )
}

export function ParamRow({ param, value, label, changedFrom }) {
  return (
    <div className="grid sm:grid-cols-[1fr_auto] gap-x-6 gap-y-2 py-3.5 border-b border-line last:border-0">
      <div className="min-w-0">
        <div className="text-[13.5px] text-ink">{cap(param?.description || humanize(param?.name))}</div>
        <div className="font-mono text-[11px] text-ink-3 mt-0.5">{param?.name}</div>
        {label && <div className={cx('mt-1.5 text-[12.5px]', label.kind === 'fact' ? 'text-blue-700' : 'text-orange-700')}>{label.kind === 'fact' ? 'From your text: ' : 'AI assumption: '}{label.statement}</div>}
      </div>
      <div className="flex sm:flex-col items-center sm:items-end gap-2">
        <div className="text-[15px] font-semibold tabular text-right max-w-[320px]">
          {changedFrom !== undefined && <span className="text-ink-3 line-through font-normal mr-2">{formatValue(changedFrom, param)}</span>}
          {formatValue(value, param)}
        </div>
        {label && <FactBadge kind={label.kind} statement={label.statement} />}
      </div>
    </div>
  )
}

/** "Week 5, session 1 of the week: Train line disruption, 45 min delay, affects …" */
export function disruptionText(d, words) {
  const kind = words.template.disruption_kinds?.find((k) => k.id === d.kind)
  const bits = [d.description || kind?.label || humanize(d.kind)]
  if (d.delay) bits.push(`${d.delay} min delay`)
  if (d.capacity != null) bits.push(`capacity ${d.capacity}`)
  if (d.people?.length) bits.push(`affects ${d.people.join(', ')}`)
  return { when: `${cap(words.period)} ${d.period}, ${words.withinPeriod(d.steps)}`, what: bits.join(', '), kind: kind?.kind || 'obstacle' }
}

export function DisruptionList({ list, words }) {
  const sorted = [...(list || [])].sort((a, b) => a.period - b.period || (a.steps?.[0] || 0) - (b.steps?.[0] || 0))
  if (!sorted.length) return <p className="text-[13px] text-ink-3">No disruptions in this term.</p>
  return (
    <ul className="flex flex-col gap-2">
      {sorted.map((d, i) => {
        const t = disruptionText(d, words)
        return (
          <li key={i} className="flex gap-3 items-center py-2.5 border-t border-line/70 first:border-0">
            <span className="grid place-items-center w-7 h-7 shrink-0 rounded-full bg-orange-50 border border-orange-100 text-orange-700 text-[12px] font-bold">{t.kind === 'capacity' ? '▼' : t.kind === 'cancellation' ? '⊘' : '⚠'}</span>
            <span className="text-[13px]"><span className="font-medium">{t.when}:</span> {t.what}</span>
          </li>
        )
      })}
    </ul>
  )
}
