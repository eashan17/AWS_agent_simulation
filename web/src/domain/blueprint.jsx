// Blueprint values, grouped by their parameter kind, each with its fact / assumption badge.
// Before approval each single value can be corrected (slice 18): the server checks it against the
// template and makes it the policymaker's fact.
import { useState } from 'react'
import { FactBadge } from './labels.jsx'
import { Button, cx } from '../ui/primitives.jsx'
import { explain } from '../lib/api.js'
import { formatValue, humanize, cap } from '../lib/words.js'

/** "From your text: …" for a fact the AI read from the policy; a correction or a requested change says so itself. */
export function labelPrefix(l) {
  if (l.kind !== 'fact') return 'AI assumption: '
  return /^(Corrected by you|Counterfactual)/.test(l.statement) ? '' : 'From your text: '
}

export const EDITABLE = ['int', 'bool', 'choice', 'text']

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
          {labelPrefix(l)}{l.statement}
        </li>
      ))}
    </ul>
  )
}

/** The input for one value, within the template's range or choices. */
export function ValueInput({ param, value, onChange, id }) {
  const base = 'rounded-xl border border-line-2 bg-white px-3 text-[13.5px] focus:outline-none focus:ring-2 focus:ring-blue-200'
  if (param.type === 'int') {
    return <input id={id} type="number" inputMode="numeric" min={param.min} max={param.max} step={1} value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} className={cx(base, 'h-9 w-28 tabular')} />
  }
  if (param.type === 'bool') {
    return (
      <select id={id} value={value ? 'yes' : 'no'} onChange={(e) => onChange(e.target.value === 'yes')} className={cx(base, 'h-9')}>
        <option value="yes">yes</option><option value="no">no</option>
      </select>
    )
  }
  if (param.type === 'choice') {
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={cx(base, 'h-9 max-w-full')}>
        {(param.choices || []).map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
      </select>
    )
  }
  return <textarea id={id} value={value ?? ''} maxLength={param.max_length || 500} rows={3} onChange={(e) => onChange(e.target.value)}
    className={cx(base, 'py-2 w-full sm:w-[320px]')} />
}

export function ParamRow({ param, value, label, changedFrom, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const canEdit = onSave && EDITABLE.includes(param?.type)
  const range = param?.type === 'int' ? `a whole number ${param.min}–${param.max}` : null
  const save = async () => {
    setSaving(true); setError(null)
    try { await onSave({ [param.name]: draft }); setEditing(false) } catch (err) { setError(err) } finally { setSaving(false) }
  }
  return (
    <div className="grid sm:grid-cols-[1fr_auto] gap-x-6 gap-y-2 py-3.5 border-b border-line last:border-0">
      <div className="min-w-0">
        <div className="text-[13.5px] text-ink">{cap(param?.description || humanize(param?.name))}</div>
        <div className="font-mono text-[11px] text-ink-3 mt-0.5">{param?.name}</div>
        {label && <div className={cx('mt-1.5 text-[12.5px]', label.kind === 'fact' ? 'text-blue-700' : 'text-orange-700')}>{labelPrefix(label)}{label.statement}</div>}
        {editing && (
          <div className="mt-3 flex flex-col gap-2">
            <label htmlFor={`edit-${param.name}`} className="text-[12px] text-ink-3">New value{range ? ` (${range})` : ''}</label>
            <ValueInput id={`edit-${param.name}`} param={param} value={draft} onChange={setDraft} />
            {error && <div role="alert" className="text-[12.5px] text-bad">{explain(error)}</div>}
            <div className="flex gap-2">
              <Button size="sm" variant="primary" onClick={save} disabled={saving || draft === ''}>{saving ? 'Saving…' : 'Save as my fact'}</Button>
              <Button size="sm" onClick={() => { setEditing(false); setDraft(value); setError(null) }} disabled={saving}>Cancel</Button>
            </div>
          </div>
        )}
      </div>
      <div className="flex sm:flex-col items-center sm:items-end gap-2">
        <div className="text-[15px] font-semibold tabular text-right max-w-[320px]">
          {changedFrom !== undefined && <span className="text-ink-3 line-through font-normal mr-2">{formatValue(changedFrom, param)}</span>}
          {formatValue(value, param)}
        </div>
        {label && <FactBadge kind={label.kind} statement={label.statement} />}
        {canEdit && !editing && <Button size="sm" onClick={() => { setDraft(value); setEditing(true) }} aria-label={`Edit ${param.name}`}>Edit</Button>}
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
