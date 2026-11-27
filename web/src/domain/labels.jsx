// The labels that carry the evidence rules. One look each, everywhere they appear.
import { Badge, cx, Dot } from '../ui/primitives.jsx'
import { IconAlert, IconCheck, IconClock, IconX } from '../ui/icons.jsx'

export const EVIDENCE = {
  'recorded fact': { short: 'Recorded fact', legend: 'what the engine recorded' },
  calculated: { short: 'Calculated', legend: 'what a rule worked out' },
  'AI interpretation': { short: 'AI interpretation', legend: "a person's own stated reason" },
}

/** recorded fact: blue, solid · calculated: ink, mono · AI interpretation: orange, dashed */
export function EvidenceLabel({ label, className }) {
  if (label === 'calculated') {
    return <span className={cx('inline-flex items-center gap-1 h-6 px-2.5 rounded-md bg-ink text-white font-mono text-[11px] tracking-wide', className)}>Σ calculated</span>
  }
  if (label === 'AI interpretation') {
    return <span className={cx('inline-flex items-center gap-1 h-6 px-2.5 rounded-full border border-dashed border-orange-500 bg-orange-50 text-orange-700 text-[11.5px] font-medium italic', className)}>“ AI interpretation</span>
  }
  return <span className={cx('inline-flex items-center gap-1 h-6 px-2.5 rounded-full bg-blue-600 text-white text-[11.5px] font-medium', className)}>● recorded fact</span>
}

export function EvidenceLegend({ className }) {
  return (
    <div className={cx('flex flex-wrap gap-x-5 gap-y-2 text-[12.5px] text-ink-2', className)}>
      {Object.entries(EVIDENCE).map(([k, v]) => (
        <span key={k} className="inline-flex items-center gap-2"><EvidenceLabel label={k} /> {v.legend}</span>
      ))}
    </div>
  )
}

/** Blueprint values: fact (from your text) vs assumption (the AI's proposal). */
export function FactBadge({ kind, statement }) {
  if (kind === 'fact') {
    return <span title={statement} className="inline-flex items-center gap-1 h-6 px-2.5 rounded-full bg-blue-600 text-white text-[11.5px] font-medium">● fact</span>
  }
  return <span title={statement} className="inline-flex items-center gap-1 h-6 px-2.5 rounded-full border border-dashed border-orange-500 bg-orange-50 text-orange-700 text-[11.5px] font-medium">◌ assumption</span>
}

export function FactLegend({ className }) {
  return (
    <div className={cx('flex flex-wrap gap-x-5 gap-y-2 text-[12.5px] text-ink-2', className)}>
      <span className="inline-flex items-center gap-2"><FactBadge kind="fact" /> from your text</span>
      <span className="inline-flex items-center gap-2"><FactBadge kind="assumption" /> the AI's proposal, check it</span>
    </div>
  )
}

export function StatusBadge({ status }) {
  if (status === 'running') return <Badge tone="blue"><Dot tone="live" /> Running</Badge>
  if (status === 'completed') return <Badge tone="ok"><IconCheck size={13} /> Completed</Badge>
  if (status === 'degraded') return <Badge tone="orange"><IconAlert size={13} /> Degraded</Badge>
  if (status === 'failed') return <Badge tone="bad"><IconX size={13} /> Failed</Badge>
  return <Badge><IconClock size={13} /> {status || 'unknown'}</Badge>
}

/** The four finding kinds (slices 8, M2, M7b). Only harm kinds are red. */
export const KIND = {
  check_failed: { label: 'Objective failure', tone: 'bad', harm: true },
  pending_at_check: { label: 'Bottleneck', tone: 'orange', harm: true },
  obligation_lost: { label: 'Obligation lost', tone: 'bad', harm: true },
  near_threshold: { label: 'Near miss', tone: 'blue', harm: false },
}
export const kindLabel = (kind) => KIND[kind]?.label || kind
export const isHarm = (f) => (f?.harm != null ? !!f.harm : !!KIND[f?.kind]?.harm)

export function KindBadge({ kind }) {
  const k = KIND[kind]
  return <Badge tone={k?.tone}>{k?.label || kind}</Badge>
}

/** Why a harm happened (slice M9): one class per harm, by rules over the records. */
export const CAUSE = {
  no_reply: { label: 'No reply from the model', tone: 'muted', note: 'An AI call failed or timed out: an infrastructure problem, not the rule.' },
  ai_mistake: { label: 'Depends on an AI mistake', tone: 'orange', note: 'A false claim or untrue correction was refused on the way: not evidence about the rule.' },
  forced: { label: 'Forced by disruptions', tone: 'orange', note: 'Delays over their slack alone were enough: piled-on disruptions, not a choice.' },
  process: { label: 'Process', tone: 'bad', note: 'A request that would have saved them was left waiting, refused late or rejected for no proof.' },
  trade_off: { label: 'Trade-off', tone: 'bad', note: 'Keeping one obligation cost the other, under how the policy reads what is exceptional.' },
  chosen: { label: 'Chosen', tone: 'muted', note: 'Misses they chose when nothing affected them.' },
}

export function CauseBadge({ cause, detail }) {
  const c = CAUSE[cause]
  if (!c) return null
  const tones = {
    bad: 'bg-bad-50 text-bad border-transparent',
    orange: 'bg-orange-50 text-orange-700 border-orange-200 border-dashed',
    muted: 'bg-mist text-ink-2 border-line',
  }
  return <span title={detail || c.note} className={cx('inline-flex items-center gap-1 h-6 px-2.5 rounded-full border text-[11.5px] font-medium', tones[c.tone])}>Why: {c.label}</span>
}

export function WithinModelBanner({ text = 'within-model evidence, not real-world causality',
  sub = 'Both runs are simulations of the same model. The differences are evidence about the model, not proof about a real college.' }) {
  return (
    <div role="note" className="glass rounded-2xl flex items-center gap-4 px-5 py-4 border-l-4 !border-l-orange-500">
      <span className="grid place-items-center w-8 h-8 rounded-full bg-orange-50 text-orange-700 text-[14px] font-bold shrink-0">!</span>
      <div>
        <div className="text-[15px] font-semibold">{text.charAt(0).toUpperCase() + text.slice(1)}</div>
        <div className="text-[13px] text-ink-2 mt-0.5">{sub}</div>
      </div>
    </div>
  )
}
