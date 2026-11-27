// "How RuleStorm reads this rule" (slices M8a, M8b): the readings the template makes of a rule like
// this one, from GET /api/templates/{id} `readings`. Some are fixed by the template (whether a kind
// of disruption is routine, leaves proof, or costs an obligation); the rest are settings with a
// default, editable here before approval and changeable in a what-if. The engine applies them
// before anyone decides. Words come only from the template.
import { Badge, Card, CardTitle, cx } from '../ui/primitives.jsx'
import { ParamRow, labelFor } from './blueprint.jsx'
import { cap, humanize } from '../lib/words.js'

/** The reading parameters shown here, not in "Policy rules": every one but a decision rule, which the fill sets from the text. */
export function readingParams(words) {
  const r = words.template.readings
  if (!r) return []
  const rules = new Set((r.request_types || []).map((t) => t.decision_rule?.parameter).filter(Boolean))
  return (r.parameters || []).filter((n) => !rules.has(n))
}

function sentence(setting, value) {
  if (!setting) return null
  const v = value ?? setting.default
  return setting.sentences?.[String(v)] || (setting.type === 'int' ? String(v) : humanize(String(v)))
}

function Fixed({ children }) {
  return <span className="text-[11px] text-ink-3 font-medium whitespace-nowrap">template reading</span>
}

export function ReadingsCard({ bp, words, onSave }) {
  const r = words.template.readings
  if (!r) return null
  const values = bp.blueprint?.values || {}
  const row = (setting) => {
    if (!setting) return null
    const p = words.param(setting.parameter)
    if (!p) return null
    const v = values[p.name] ?? setting.default
    return <ParamRow key={p.name} param={p} value={v} label={labelFor(bp, p.name, null)} onSave={onSave} />
  }
  const request = words.terms.request || 'request'
  const kinds = (r.disruption_kinds || []).filter((k) => k.kind === 'obstacle' || k.kind === 'conflict')
  return (
    <Card>
      <CardTitle title="How RuleStorm reads this rule"
        sub={`What the simulation takes the rule to mean. The template fixes some readings; the rest are settings with a default you can change here or in a what-if. The engine applies them before anyone decides, and every person is told them.`} />

      {(r.request_types || []).map((t) => (
        <div key={t.id} className="mb-4">
          <h4 className="text-[13.5px] font-semibold">{cap(t.label)}s</h4>
          <p className="text-[13px] text-ink-2 mt-1">
            Decided by the {t.decider.toLowerCase()} {t.decided_by === 'rule' ? '(by a fixed rule, no AI)' : '(an AI person, who sees what caused each miss)'}
            {t.endorsed_by ? `, after the ${t.endorsed_by.toLowerCase()}'s consent` : ''}.
            {t.decision_rule ? ` ${sentence(t.decision_rule, values[t.decision_rule.parameter])}` : ''}
          </p>
          <ul className="mt-2 text-[13px] flex flex-col gap-1">
            {t.exceptional && <li><span className="text-ink-3">What counts as exceptional: </span>{sentence(t.exceptional, values[t.exceptional.parameter])}</li>}
            {t.proof && <li><span className="text-ink-3">Proof: </span>{sentence(t.proof, values[t.proof.parameter])}</li>}
            {t.deadline && <li><span className="text-ink-3">Filing deadline: </span>{Number(values[t.deadline.parameter] ?? t.deadline.default) ? `within ${values[t.deadline.parameter] ?? t.deadline.default} ${words.period}(s) of the ${words.step} it covers` : 'none'}</li>}
          </ul>
          <div className="mt-2">{[t.exceptional, t.proof, t.deadline].map(row)}</div>
        </div>
      ))}

      {(r.counts || []).filter((c) => c.excused).map((c) => (
        <div key={c.count} className="mb-4">
          <h4 className="text-[13.5px] font-semibold">How an excused {words.step} counts in {c.label}</h4>
          <p className="text-[13px] text-ink-2 mt-1">An approved {request}'s {words.step}s: {sentence(c.excused, values[c.excused.parameter])}.</p>
          <div className="mt-1">{row(c.excused)}</div>
        </div>
      ))}

      {kinds.length > 0 && (
        <div>
          <h4 className="text-[13.5px] font-semibold flex items-center gap-2">What each disruption is <Fixed /></h4>
          <div className="overflow-x-auto -mx-2 mt-2">
            <table className="w-full text-[13px] min-w-[520px]">
              <thead><tr className="text-left text-ink-3 text-[12px]">
                <th className="font-medium px-2 py-1.5">Disruption</th><th className="font-medium px-2 py-1.5">Routine?</th>
                <th className="font-medium px-2 py-1.5">Leaves proof?</th><th className="font-medium px-2 py-1.5">What keeping the rule costs</th>
              </tr></thead>
              <tbody>
                {kinds.map((k) => (
                  <tr key={k.id} className="border-t border-line align-top">
                    <td className="px-2 py-2 font-medium">{cap(k.label)}</td>
                    <td className="px-2 py-2">{k.routine ? <Badge tone="orange" className="!h-5 !text-[11px]">routine: could be planned around</Badge> : <span className="text-ink-2">no: outside their control</span>}</td>
                    <td className="px-2 py-2">{k.leaves_proof ? 'yes' : <span className="text-ink-3">no</span>}</td>
                    <td className="px-2 py-2">{k.obligation ? <span>their {k.obligation.label}; past their limit, <span className={cx('font-medium text-bad')}>{k.obligation.lost_label}</span></span> : <span className="text-ink-3">nothing</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  )
}
