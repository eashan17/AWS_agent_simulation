// Analysis pieces: finding cards, the accent finding card, the calculation panel, the evidence
// timeline and the records chart. Hierarchy: the result first, then how it happened.
import { useMemo, useState } from 'react'
import { Badge, Button, Card, CardTitle, cx, IdTag } from '../ui/primitives.jsx'
import { IconArrow, IconChain } from '../ui/icons.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { KindBadge } from './labels.jsx'
import { cap, humanize, pct } from '../lib/words.js'

const CMP = { '>=': '≥', '<=': '≤', '>': '>', '<': '<' }

export function figure(count) {
  if (!count) return '—'
  if (count.kind === 'rate') return `${count.met} / ${count.due} = ${pct(count.value)}`
  return `${count.value}`
}
const big = (count) => (count?.kind === 'rate' ? pct(count.value) : count?.value ?? '—')

/** Bottleneck findings also show the figure if the waiting requests were approved, when it differs. */
function ifApproved(f) {
  const a = f.count_if_pending_approved
  if (!a || a.value === f.count?.value) return null
  return a
}

/** One finding in the Findings grid: result first, then who, then the trail. */
export function FindingCard({ f, words, onOpen, check }) {
  const alt = ifApproved(f)
  return (
    <Card className="flex flex-col">
      <div className="flex items-center justify-between gap-3">
        <KindBadge kind={f.kind} />
        <span className="text-[12px] text-ink-3">{cap(words.period)} {f.period} · {f.check_label}</span>
      </div>
      <h3 className="mt-4 text-[17px] font-semibold leading-snug tracking-[-0.01em]">{f.title}</h3>
      <div className="mt-5 flex items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <PersonAvatar colour={words.colour(f.person)} size={40} mood="sad" />
          <div>
            <div className="text-[14px] font-medium">{words.name(f.person)}</div>
            <div className="text-[12.5px] text-ink-3">{words.label(f.person)}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[34px] leading-none font-normal tracking-[-0.03em] tabular">{big(f.count)}</div>
          <div className="text-[12.5px] text-ink-3 mt-1">{f.count?.kind === 'rate' ? `${f.count.met} / ${f.count.due}` : words.terms.count}{check ? ` · needs ${CMP[check.comparison] || ''} ${check.threshold}${f.count?.kind === 'rate' ? '%' : ''}` : ''}</div>
        </div>
      </div>
      {alt && <p className="mt-3 text-[13px] text-orange-700">{pct(alt.value)} if {f.pending_requests.join(', ')} {f.pending_requests.length > 1 ? 'were' : 'was'} approved in time.</p>}
      <div className="mt-5 pt-4 border-t border-line/70 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-4 text-[12.5px] text-ink-3">
          <span className="inline-flex items-center gap-1.5"><IconChain size={14} /> {f.chain.length} linked events</span>
          <span>{f.disruptions.length} disruption{f.disruptions.length === 1 ? '' : 's'}</span>
          <IdTag id={f.finding_id} label="Finding" />
        </div>
        <Button iconRight={<IconArrow size={16} />} onClick={onOpen}>Show the evidence</Button>
      </div>
    </Card>
  )
}

/** The one accent card on a screen (Wattbank's "84% self-powered"): the finding's result. */
export function HeroFinding({ f, words, onOpen, action = 'Show the evidence', check }) {
  const alt = ifApproved(f)
  return (
    <section className="accent-card relative overflow-hidden rounded-[var(--radius-card)] p-6 flex flex-col min-h-[300px]">
      <div className="flex items-center gap-2 text-[12px] font-medium text-ink/70">
        <span className="grid place-items-center w-5 h-5 rounded-full bg-ink text-white text-[10px]">!</span>
        {f.kind === 'check_failed' ? 'Objective failure' : 'Bottleneck'} · found by rules from the records
      </div>
      <div className="mt-auto pt-10">
        <div className="flex items-center gap-2.5">
          <PersonAvatar colour={words.colour(f.person)} size={34} mood="sad" />
          <span className="text-[14px] font-medium">{words.name(f.person)}</span>
          <span className="text-[13px] text-ink/60">· {words.label(f.person)}</span>
        </div>
        <p className="mt-3 text-[30px] leading-[1.12] font-normal tracking-[-0.02em]">
          is at <span className="font-medium tabular">{big(f.count)}</span> at the {words.period} {f.period} check, <em className="font-normal">{f.outcome}</em>
        </p>
        <p className="mt-2 text-[13.5px] text-ink/70 max-w-md">
          {f.count?.kind === 'rate' ? `${f.count.met} of ${f.count.due} counted ${words.step}s` : figure(f.count)}
          {check ? `, against ${CMP[check.comparison] || ''} ${check.threshold}${f.count?.kind === 'rate' ? '%' : ''}` : ''}.
          {alt ? ` ${pct(alt.value)} if the waiting ${words.terms.requests} were approved.` : ''}
        </p>
        {onOpen && (
          <button type="button" onClick={onOpen} className="mt-5 inline-flex items-center gap-2 h-10 px-4 rounded-full bg-white/75 hover:bg-white text-[14px] font-medium transition backdrop-blur">
            {action} <IconArrow size={16} />
          </button>
        )}
      </div>
    </section>
  )
}

/** The check's calculation as a measure against its threshold (Wattbank's chart with the "Optimal" pill). */
export function CalcPanel({ calc, words }) {
  if (!calc) return null
  const r = calc.recorded || {}
  const a = calc.if_pending_approved
  const rate = calc.kind === 'rate'
  const max = rate ? 100 : Math.max(1, r.value, calc.threshold) * 1.3
  const pos = (v) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`
  const passed = calc.outcome && calc.outcome === words.terms.check_passed
  const altDiffers = a && a.value !== r.value
  return (
    <Card className="flex flex-col">
      <CardTitle title="The calculation" sub={calc.matches_recorded ? "✓ Recomputed from this run's records, and it matches what the engine recorded" : "Worked out from this run's records"} />
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <div className="text-[12.5px] text-ink-3 mb-1">{cap(humanize(calc.count))}</div>
          <div className="font-mono text-[30px] leading-none tracking-tight tabular">{rate ? <>{r.met} <span className="text-ink-3">/</span> {r.due} <span className="text-ink-3">=</span> </> : null}<span className={passed ? 'text-ok' : 'text-bad'}>{rate ? pct(r.value) : r.value}</span></div>
        </div>
        <div className="pb-0.5">
          <div className="text-[12.5px] text-ink-3 mb-1">Rule</div>
          <div className="font-mono text-[18px]">needs {CMP[calc.comparison] || calc.comparison} {calc.threshold}{rate ? '%' : ''}</div>
        </div>
        <div className="pb-0.5 ml-auto">
          <Badge tone={passed ? 'ok' : 'bad'} className="!h-7 !text-[13px]">→ {calc.outcome}</Badge>
        </div>
      </div>
      {/* the measure against the threshold */}
      <div className="relative mt-10 mb-2" aria-hidden>
        <div className="h-3 rounded-full bg-white/80 border border-line overflow-hidden">
          <div className="h-full rounded-full" style={{ width: pos(r.value), background: passed ? 'var(--color-blue-400)' : 'linear-gradient(90deg, var(--color-orange-200), var(--color-orange-500))' }} />
        </div>
        {altDiffers && <div className="absolute top-0 h-3 w-0.5 bg-blue-600" style={{ left: pos(a.value) }} />}
        <div className="absolute -top-8 -translate-x-1/2" style={{ left: pos(calc.threshold) }}>
          <span className="inline-block px-2.5 h-6 leading-6 rounded-full bg-orange-500 text-white text-[11.5px] font-semibold whitespace-nowrap">needs {CMP[calc.comparison] || ''} {calc.threshold}{rate ? '%' : ''}</span>
        </div>
        <div className="absolute top-[-6px] h-6 w-0.5 bg-orange-500 -translate-x-1/2" style={{ left: pos(calc.threshold) }} />
        <div className="flex justify-between font-mono text-[10.5px] text-ink-3 mt-1.5"><span>0</span><span>{rate ? '100%' : Math.round(max)}</span></div>
      </div>
      <div className="mt-auto pt-4 grid sm:grid-cols-2 gap-3 text-[13px]">
        <div className="rounded-2xl bg-white/55 border border-white px-4 py-3">
          <div className="text-ink-3 text-[12px]">As recorded</div>
          <div className="font-mono mt-0.5">{r.text}</div>
        </div>
        <div className="rounded-2xl bg-white/55 border border-white px-4 py-3">
          <div className="text-ink-3 text-[12px]">If waiting {words.terms.requests} were approved</div>
          <div className="font-mono mt-0.5">{altDiffers ? a.text : `the same: none were waiting`}</div>
        </div>
      </div>
    </Card>
  )
}

const LABEL_DOT = {
  'recorded fact': 'bg-blue-600',
  calculated: 'bg-ink rounded-[3px]',
  'AI interpretation': 'bg-white border-2 border-orange-500',
}
const LABEL_TEXT = {
  'recorded fact': 'text-blue-700',
  calculated: 'text-ink-2 font-mono',
  'AI interpretation': 'text-orange-700 italic',
}

/** "…, session 9 (week 5)" is already in the time column, so it's dropped from the sentence. */
function tidy(text, words) {
  if (!text) return ''
  const re = new RegExp(`,?\\s*${words.step} \\d+ \\(${words.period} \\d+\\)`, 'g')
  return text.replace(re, '').replace(/\s+,/g, ',').trim()
}

/** How it happened: one panel, grouped by when, with weight given to what matters. */
export function EvidenceTimeline({ steps, words, onFocus, focus }) {
  const groups = []
  let key = null
  for (const s of steps) {
    const k = `${s.period}:${s.step ?? 'end'}`
    if (k !== key) { groups.push({ k, period: s.period, step: s.step, items: [] }); key = k }
    groups[groups.length - 1].items.push(s)
  }
  return (
    <ol className="flex flex-col">
      {groups.map((g, gi) => (
        <li key={g.k} className="grid grid-cols-[88px_minmax(0,1fr)] sm:grid-cols-[120px_minmax(0,1fr)] gap-x-4" onMouseEnter={() => onFocus?.(g.period)}>
          <div className="pt-0.5 text-right">
            <div className={cx('text-[14px] font-semibold', focus === g.period && 'text-orange-700')}>{cap(words.period)} {g.period}</div>
            <div className="text-[12px] text-ink-3">{g.step == null ? `end of ${words.period}` : `${words.step} ${g.step}`}</div>
          </div>
          <ul className={cx('relative pl-7 pb-7', gi === groups.length - 1 && 'pb-0')}>
            <span className="absolute left-[7px] top-2 bottom-0 w-px bg-ink-4/40" aria-hidden />
            {g.items.map((s) => {
              const isCheck = !!s.calculation
              const isDisruption = s.type === 'obstacle' || s.type === 'capacity_changed' || s.type === 'occurrence_cancelled'
              const person = s.actor && (words.travellers.includes(s.actor) || words.staff.includes(s.actor)) ? s.actor : null
              const minor = s.type === 'many_missed' || s.type === 'duty_planned'
              return (
                <li key={s.event_id} className={cx('relative', minor ? 'pb-3' : 'pb-5', 'last:pb-0')}>
                  <span className={cx('absolute -left-7 top-1.5 w-[15px] h-[15px] rounded-full ring-4 ring-[var(--glass-strong)]',
                    isDisruption ? 'bg-orange-500' : LABEL_DOT[s.label])} aria-hidden />
                  <div className={cx(isCheck && 'rounded-2xl px-4 py-3 -mx-1 border border-white', isCheck && 'bg-[image:var(--wash-orange)]')}>
                    <div className="flex items-start gap-3">
                      <p className={cx('flex-1 leading-snug', isCheck ? 'text-[15px] font-semibold' : isDisruption ? 'text-[14.5px] font-medium' : minor ? 'text-[13px] text-ink-2' : 'text-[14px] text-ink')}>
                        {person && !minor && <span className="inline-block align-[-5px] mr-1.5"><PersonAvatar colour={words.colour(person)} ai={words.isAI(person)} size={20} /></span>}
                        {isDisruption && <span className="text-orange-500 mr-1" aria-hidden>⚠</span>}
                        {tidy(s.text, words)}
                      </p>
                      <span className={cx('shrink-0 text-[11.5px] mt-0.5', LABEL_TEXT[s.label])}>{s.label}</span>
                    </div>
                    {s.interpretation && (
                      <blockquote className="mt-2 pl-3 border-l-2 border-dashed border-orange-400 text-[14px] leading-relaxed text-ink-2 italic">
                        “{s.interpretation}”
                        <span className="not-italic block mt-1 text-[12px] text-ink-3">{humanize(s.actor)}'s own stated reason</span>
                      </blockquote>
                    )}
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-ink-3 break-all">
                      <span>{s.event_id}</span>
                      {Object.entries(s.state_change || {}).map(([k, v]) => (
                        <span key={k}>{k}: {v?.from == null ? '—' : String(v.from)} → <span className="text-ink-2">{v?.to == null ? '—' : String(v.to)}</span></span>
                      ))}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        </li>
      ))}
    </ol>
  )
}

/** Cumulative recorded misses per person by period, from the run's own records (corrections applied). */
export function useMissSeries(events, words) {
  return useMemo(() => {
    const spp = words.cal.steps_per_period || 1
    const rec = {}
    const obstaclePeriods = new Set()
    const checkPeriods = new Set()
    for (const e of events) {
      for (const [k, v] of Object.entries(e.state_change || {})) {
        if (!k.startsWith('record.')) continue
        const [, , person, step] = k.split('.')
        ;(rec[person] ||= {})[Number(step)] = v?.to
      }
      if (e.type === 'obstacle') obstaclePeriods.add(e.period)
      if (e.type === 'check_evaluated') checkPeriods.add(e.period)
    }
    const series = words.travellers.map((id) => {
      const per = Array.from({ length: words.periods }, () => 0)
      for (const [step, out] of Object.entries(rec[id] || {})) if (out === 'missed') per[Math.ceil(Number(step) / spp) - 1] += 1
      let acc = 0
      return { id, values: per.map((x) => (acc += x)) }
    })
    return { series, obstaclePeriods, checkPeriods }
  }, [events, words])
}

export function MissChart({ events, words, highlight }) {
  const { series, obstaclePeriods, checkPeriods } = useMissSeries(events, words)
  const [hover, setHover] = useState(null)
  const W = 720
  const H = 280
  const L = 40
  const R = 16
  const T = 34
  const B = 34
  const n = words.periods
  const maxV = Math.max(2, ...series.flatMap((s) => s.values))
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, n - 1)
  const y = (v) => T + (1 - v / maxV) * (H - T - B)
  // whole numbers: every count up to 5, else 0 · about half · max
  const ticks = maxV <= 5 ? Array.from({ length: maxV + 1 }, (_, i) => i) : [0, Math.ceil(maxV / 2), maxV]
  // equal lines would hide each other: nudge each series a little, and draw the highlighted one last
  const nudge = Object.fromEntries(series.map((s, i) => [s.id, (i - (series.length - 1) / 2) * 2.5]))
  const line = (vals, id) => vals.map((v, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(v) + (nudge[id] || 0)}`).join(' ')
  const hl = highlight && series.find((s) => s.id === highlight)
  const ordered = hl ? [...series.filter((s) => s.id !== highlight), hl] : series
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
        aria-label={`${words.terms.missed_plural || 'misses'} recorded per person by ${words.period}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - r.left) / r.width) * W
          setHover(Math.max(0, Math.min(n - 1, Math.round(((px - L) / (W - L - R)) * (n - 1)))))
        }}>
        {/* disruption periods */}
        {[...obstaclePeriods].map((p) => (
          <rect key={p} x={x(p - 1) - (W - L - R) / (n - 1) / 2} y={T} width={(W - L - R) / (n - 1)} height={H - T - B} fill="var(--color-orange-50)" />
        ))}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
            <text x={L - 10} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--color-ink-3)" className="tabular">{t}</text>
          </g>
        ))}
        {Array.from({ length: n }).map((_, i) => (
          <text key={i} x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--color-ink-3)">{i + 1}</text>
        ))}
        <defs>
          <linearGradient id="miss-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--color-blue-200)" stopOpacity=".75" />
            <stop offset="1" stopColor="var(--color-blue-100)" stopOpacity=".1" />
          </linearGradient>
        </defs>
        {hl && <path d={`${line(hl.values, hl.id)} L ${x(n - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`} fill="url(#miss-area)" />}
        {ordered.map((s) => (
          <path key={s.id} d={line(s.values, s.id)} fill="none" stroke={words.colour(s.id)} strokeWidth={highlight === s.id ? 3 : 1.75} strokeLinejoin="round" strokeLinecap="round" opacity={highlight && highlight !== s.id ? 0.6 : 1} />
        ))}
        {hl && hl.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v) + (nudge[hl.id] || 0)} r="4" fill="var(--color-ink)" stroke="#fff" strokeWidth="1.5" />)}
        {[...checkPeriods].map((p) => (
          <g key={p} transform={`translate(${x(p - 1)} ${T - 16})`}>
            <line y1="12" y2={H - T - B + 16} stroke="var(--color-orange-500)" strokeDasharray="3 4" />
            <rect x="-26" y="-4" width="52" height="22" rx="11" fill="var(--color-orange-500)" />
            <text y="11" textAnchor="middle" fontSize="11" fontWeight="600" fill="#fff">Check</text>
          </g>
        ))}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--color-ink)" strokeOpacity=".25" />
            {series.map((s) => <circle key={s.id} cx={x(hover)} cy={y(s.values[hover]) + (nudge[s.id] || 0)} r="4.5" fill="#fff" stroke={words.colour(s.id)} strokeWidth="2.5" />)}
          </g>
        )}
        <text x={W - R} y={H - 0} textAnchor="end" fontSize="10.5" fill="var(--color-ink-3)">{words.period}</text>
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2 text-[12.5px]">
        {series.map((s) => (
          <span key={s.id} className="inline-flex items-center gap-1.5">
            <span className="w-3 h-1 rounded-full" style={{ background: words.colour(s.id) }} />
            <span className="text-ink-2">{words.name(s.id)}</span>
            <span className="font-mono text-ink-3 tabular">{hover != null ? s.values[hover] : s.values[n - 1]}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5 text-ink-3"><span className="w-3 h-3 rounded bg-orange-50 border border-orange-100" /> {words.period}s with a disruption</span>
      </div>
      <div className="sr-only"><table>
        <caption>Cumulative {words.terms.missed_plural} by {words.period}</caption>
        <thead><tr><th>Person</th>{Array.from({ length: n }).map((_, i) => <th key={i}>{words.period} {i + 1}</th>)}</tr></thead>
        <tbody>{series.map((s) => <tr key={s.id}><th>{s.id}</th>{s.values.map((v, i) => <td key={i}>{v}</td>)}</tr>)}</tbody>
      </table></div>
    </div>
  )
}
