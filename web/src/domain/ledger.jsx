// Who carried the rule (slices M3, M9): per person their margin to the step that harms them, their
// misses by kind, and the obligations it cost, from GET /api/runs/{id}/ledger. Rules over the run's
// records, no AI. Words come from the template.
import { Badge, cx } from '../ui/primitives.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { cap, pct } from '../lib/words.js'

/** A person's margin to the step that harms them: a single check's spare, or a ladder's last step. */
export function harmfulMargin(p) {
  const last = {}
  for (const m of p.checks || []) if (m.ladder_step != null) last[m.check] = Math.max(last[m.check] || 0, m.ladder_step)
  const spares = (p.checks || []).filter((m) => m.spare != null && (m.ladder_step == null || m.ladder_step === last[m.check]))
  if (!spares.length) return null
  return spares.reduce((a, b) => (b.spare < a.spare ? b : a))
}

/** The figure at the check, as a percentage when the template's count is one. */
function figureOf(m, words) {
  if (m.value == null) return '—'
  return (words.terms.count || '').includes('%') ? pct(m.value) : `${m.value}`
}

/** One row per person, closest to being harmed first. */
export function LedgerTable({ book, words, onPerson }) {
  const people = [...(book?.people || [])].sort((a, b) => (harmfulMargin(a)?.spare ?? 99) - (harmfulMargin(b)?.spare ?? 99))
  const missed = words.terms.missed_plural || 'misses'
  return (
    <div className="overflow-x-auto -mx-2">
      <table className="w-full text-[13px] min-w-[620px]">
        <thead><tr className="text-left text-ink-3 text-[12px]">
          <th className="font-medium px-2 py-2">Person</th>
          <th className="font-medium px-2 py-2">Margin</th>
          <th className="font-medium px-2 py-2">{cap(missed)}</th>
          <th className="font-medium px-2 py-2">{cap(words.terms.requests || 'requests')}</th>
          <th className="font-medium px-2 py-2">Obligations</th>
        </tr></thead>
        <tbody>
          {people.map((p) => {
            const m = harmfulMargin(p)
            const harmed = m && m.spare <= 0
            const a = p.absences
            return (
              <tr key={p.person} className="border-t border-line align-top">
                <td className="px-2 py-2.5">
                  <button type="button" onClick={() => onPerson?.(p.person)} className="flex items-center gap-2 text-left rounded-xl hover:bg-white/60 pr-2" aria-label={`Everything about ${words.name(p.person)}`}>
                    <PersonAvatar colour={words.colour(p.person)} size={26} mood={harmed ? 'sad' : 'idle'} />
                    <span className="font-medium text-blue-700">{words.name(p.person)}</span>
                  </button>
                </td>
                <td className="px-2 py-2.5">
                  {m ? (
                    <span className="inline-flex items-center gap-2 flex-wrap">
                      <span className={cx('tabular font-semibold', harmed ? 'text-bad' : m.spare <= 1 ? 'text-orange-700' : 'text-ok')}>
                        {harmed ? `reached ${m.outcome}` : `${m.spare} to spare`}
                      </span>
                      <span className="text-ink-3">{figureOf(m, words)} at {m.where}{harmed ? '' : `, before ${m.outcome}`}</span>
                    </span>
                  ) : <span className="text-ink-3">no figure counted</span>}
                </td>
                <td className="px-2 py-2.5 tabular">{a.total} <span className="text-ink-3">(excused {a.excused}, unexcused {a.unexcused}{a.pending ? `, waiting ${a.pending}` : ''})</span></td>
                <td className="px-2 py-2.5 tabular">{p.requests.filed} filed{p.requests.rejected ? <span className="text-ink-3">, {p.requests.rejected} rejected</span> : ''}{p.requests.refused ? <span className="text-ink-3">, {p.requests.refused} refused</span> : ''}</td>
                <td className="px-2 py-2.5">
                  {p.obligations.lost ? <Badge tone="bad" className="!h-5 !text-[11px]">{p.obligations.lost} lost</Badge> : null}
                  {p.obligations.missed ? <span className="tabular ml-1">{p.obligations.missed} missed</span> : null}
                  {!p.obligations.lost && !p.obligations.missed && <span className="text-ink-3">none missed</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** The Summary headline when nobody was harmed: who carried the rule, and who came closest. */
export function WhoCarried({ book, words, onPerson, actions }) {
  const people = book?.people || []
  const closest = people.map((p) => ({ p, m: harmfulMargin(p) })).filter((x) => x.m).sort((a, b) => a.m.spare - b.m.spare)[0]
  const near = (book?.findings || []).filter((f) => f.kind === 'near_threshold').length
  const lostAny = people.some((p) => p.obligations.missed)
  return (
    <section className="glass rounded-[var(--radius-card)] p-6 flex flex-col min-h-[300px]">
      <div className="flex items-center gap-2 text-[12px] font-medium text-ink-2"><span className="w-2 h-2 rounded-full bg-ok" /> No harm in this run · found by rules from the records</div>
      <h3 className="mt-6 text-[28px] font-normal tracking-[-0.02em] leading-tight">Who carried this rule</h3>
      <p className="mt-2 text-[14px] text-ink-2">
        Nobody failed a check, lost an obligation or was left waiting at a check.
        {closest ? ` ${words.name(closest.p.person)} came closest: ${closest.m.spare} ${closest.m.spare === 1 ? 'miss' : 'misses'} to spare before ${closest.m.outcome}.` : ''}
        {near ? ` ${near} near miss${near === 1 ? '' : 'es'}.` : ''}
        {lostAny ? ' Keeping the rule cost some people part of their obligations; see the last column.' : ''}
      </p>
      <div className="mt-4"><LedgerTable book={book} words={words} onPerson={onPerson} /></div>
      {actions && <div className="mt-5 flex flex-wrap gap-2">{actions}</div>}
    </section>
  )
}
