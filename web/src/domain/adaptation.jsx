// How the AI people adapted (slice 19): from GET /api/runs/{id}/adaptations, which finds them by
// rules over the run's records. Shown as a badge on the timeline and as a list per person.
import { Badge, cx } from '../ui/primitives.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { EvidenceLabel } from './labels.jsx'

export const KIND_TEXT = {
  value_changed: 'changed their own value',
  first_action: 'did something new',
  strategy_shift: 'changed strategy',
}

/** event_id -> the kind of adaptation it is, for the timeline badge. */
export function adaptedMap(items) {
  const out = {}
  for (const a of items || []) out[a.event_id] = a.kind
  return out
}

export function AdaptedBadge({ kind }) {
  if (!kind) return null
  return <Badge tone={kind === 'value_changed' ? 'orange' : 'blue'} className="!h-5 !text-[10.5px] ml-1.5 align-[1px]">adapted: {KIND_TEXT[kind]}</Badge>
}

function Item({ a, words }) {
  return (
    <li className="flex flex-col gap-1.5 py-2.5 border-t border-line first:border-0">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge tone={a.kind === 'value_changed' ? 'orange' : 'blue'} className="!h-5 !text-[11px]">{KIND_TEXT[a.kind]}</Badge>
        <EvidenceLabel label={a.label} />
        <span className="font-mono text-[10.5px] text-ink-4">{a.event_id}</span>
      </div>
      <p className="text-[13px]">{a.text}</p>
      {a.kind === 'strategy_shift' && (
        <div className="grid sm:grid-cols-2 gap-2 text-[12.5px]">
          <div className="rounded-xl bg-mist border border-line px-3 py-2"><div className="eyebrow !text-[10px] mb-0.5">Before · {a.previous_event_id}</div><span className="italic text-ink-2">“{a.from}”</span></div>
          <div className="rounded-xl bg-white/80 border border-orange-100 border-dashed px-3 py-2"><div className="eyebrow !text-[10px] mb-0.5">Now</div><span className="italic">“{a.to}”</span></div>
        </div>
      )}
      {a.effects?.length > 0 && (
        <ul className="flex flex-col gap-1">
          {a.effects.map((x, i) => (
            <li key={i} className="text-[12.5px] rounded-xl bg-orange-50/70 border border-orange-100 px-3 py-1.5">
              <span className="font-medium">What it changed later: </span>{x.text}
              <span className="font-mono text-[10.5px] text-ink-3 ml-1.5">{x.event_ids.filter(Boolean).join(' → ')}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

/** Per person, in run order. Value changes (with their effect) first: they are the strongest evidence. */
export function AdaptationList({ items, words, className }) {
  const by = {}
  for (const a of items || []) (by[a.person] ||= []).push(a)
  const order = [...words.travellers, ...words.staff].filter((id) => by[id])
  if (!order.length) return <p className={cx('text-[13px] text-ink-3', className)}>No one changed their own values, did something new or changed their stated strategy in this run.</p>
  return (
    <div className={cx('grid lg:grid-cols-2 gap-3', className)}>
      {order.map((id) => {
        const list = [...by[id]].sort((a, b) => (a.kind === 'value_changed' ? 0 : 1) - (b.kind === 'value_changed' ? 0 : 1))
        return (
          <section key={id} className="rounded-2xl bg-white/70 border border-white p-4 min-w-0">
            <div className="flex items-center gap-2.5 mb-1">
              <PersonAvatar colour={words.colour(id)} ai={words.isAI(id)} size={28} />
              <div className="min-w-0"><div className="font-medium text-[13.5px]">{words.name(id)}</div><div className="text-[12px] text-ink-3 truncate">{words.label(id)}</div></div>
              <span className="ml-auto text-[12px] text-ink-3 tabular">{list.length}</span>
            </div>
            <ul>{list.map((a) => <Item key={a.event_id + a.kind} a={a} words={words} />)}</ul>
          </section>
        )
      })}
    </div>
  )
}
