// Repeated runs (slice 21): the same blueprint run several times, read as "how often".
// POST /api/blueprints/{id}/repeats answers at once; GET /api/repeats/{id} is polled while running.
import { useEffect, useState } from 'react'
import { Badge, Banner, Button, Card, CardTitle, Dot, EmptyState, IdTag, Progress, cx } from '../ui/primitives.jsx'
import { IconLock, IconRestart } from '../ui/icons.jsx'
import { ApiErrorBanner, LoadingBlock } from './feedback.jsx'
import { CAUSE, CauseBadge, KindBadge, WithinModelBanner } from './labels.jsx'
import { api } from '../lib/api.js'
import { href, navigate } from '../lib/router.js'
import { setSession, useSession } from '../lib/session.js'
import { cap, pct } from '../lib/words.js'

const CHOICES = [2, 3, 5]

export function useRepeat(id) {
  const [state, setState] = useState({ data: null, error: null })
  useEffect(() => {
    if (!id) { setState({ data: null, error: null }); return }
    let alive = true
    let timer = null
    const tick = async () => {
      try {
        const data = await api.getRepeat(id)
        if (!alive) return
        setState({ data, error: null })
        if (data.status === 'running') timer = setTimeout(tick, 3000)
      } catch (error) {
        if (!alive) return
        setState((s) => ({ data: s.data, error }))
        if (error.kind !== 'notfound') timer = setTimeout(tick, 3000)
      }
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [id])
  return state
}

/** Start repeats and open them; used by the tab and by Analysis's "Run it again". */
export async function startRepeats(blueprintId, times, includeRun) {
  const r = await api.startRepeats(blueprintId, times, includeRun)
  setSession((st) => ({ repeats: { ...(st.repeats || {}), [blueprintId]: r.id } }))
  navigate(`/blueprint/${blueprintId}/repeat/${r.id}`)
  return r
}

function fmt(v, kind) {
  if (v == null) return '—'
  return kind === 'pct' ? pct(v) : String(v)
}

function Summary({ s, words }) {
  return (
    <>
      <Card>
        <CardTitle title="How often each person failed the check" sub={`Out of ${s.runs} runs with exactly the same conditions, policy and people`} />
        <ul className="flex flex-col gap-3">
          {s.people.map((p) => (
            <li key={p.person} className="grid sm:grid-cols-[180px_1fr] gap-2 items-center">
              <div>
                <div className="font-medium text-[13.5px]">{words.name(p.person)}</div>
                <div className="text-[12px] text-ink-3 truncate">{words.label(p.person)}</div>
              </div>
              <div className="flex flex-col gap-1.5 min-w-0">
                <div className="flex items-center gap-3">
                  <div className="h-2.5 flex-1 rounded-full bg-white border border-line overflow-hidden" aria-hidden>
                    <div className={cx('h-full rounded-full', p.failed ? 'bg-bad' : 'bg-ok')} style={{ width: `${p.checked ? Math.max(4, (p.failed / p.checked) * 100) : 0}%` }} />
                  </div>
                  <span className={cx('text-[13px] font-semibold tabular shrink-0', p.failed ? 'text-bad' : 'text-ok')}>
                    {p.failed ? `${words.terms.check_failed} in ${p.failed} of ${p.checked}` : `${words.terms.check_passed} in all ${p.checked}`}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 text-[11.5px]">
                  {p.values.map((v) => (
                    <a key={v.run_id} href={href(`/run/${v.run_id}/analysis`)} className={cx('rounded-full px-2 py-0.5 border tabular hover:underline', v.passed ? 'bg-ok-50 border-transparent text-ok' : 'bg-bad-50 border-transparent text-bad')}>
                      {fmt(v.value, 'pct')} {v.passed ? '✓' : '✕'} <span className="font-mono text-ink-3">{v.run_id}</span>
                    </a>
                  ))}
                  {p.lowest != null && <span className="text-ink-3 self-center">lowest {pct(p.lowest)} · mean {pct(p.mean)} · highest {pct(p.highest)}</span>}
                  {p.margin?.lowest != null && <span className="text-ink-3 self-center">· {p.margin.lowest === p.margin.highest ? `${p.margin.lowest}` : `${p.margin.lowest} to ${p.margin.highest}`} {p.margin.highest === 1 ? 'miss' : 'misses'} to spare{p.margin.lowest === p.margin.highest ? ' in every run' : ` (mean ${p.margin.mean})`}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Card>
      <div className="grid md:grid-cols-[260px_1fr] gap-4">
        <Card>
          <CardTitle title="Findings" sub="Runs in which each kind appeared" />
          {s.findings.length ? (
            <ul className="flex flex-col gap-2 text-[13px]">
              {s.findings.map((f) => (
                <li key={f.kind} className="flex items-center justify-between gap-2">
                  <KindBadge kind={f.kind} />
                  <span className="tabular font-semibold">{f.runs} of {s.runs}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-[13px] text-ink-3">No finding in any run.</p>}
          {s.cause_classes?.length > 0 && (
            <>
              <h4 className="eyebrow !text-[10.5px] mt-5 mb-2">Why each harm happened</h4>
              <ul className="flex flex-col gap-2 text-[13px]">
                {s.cause_classes.map((c) => (
                  <li key={c.cause_class} className="flex items-center justify-between gap-2" title={CAUSE[c.cause_class]?.note}>
                    <CauseBadge cause={c.cause_class} />
                    <span className="tabular font-semibold">{c.harms} harm{c.harms === 1 ? '' : 's'}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {s.obligations_lost != null && <p className="mt-4 text-[13px] text-ink-2">Obligations lost across the runs: <span className={cx('tabular font-semibold', s.obligations_lost ? 'text-bad' : 'text-ok')}>{s.obligations_lost}</span></p>}
        </Card>
        <Card className="!p-0 overflow-hidden">
          <div className="px-5 pt-5"><CardTitle className="!mb-3" title="The spread of each measure" sub="Lowest · mean · highest across the runs" /></div>
          <div className="overflow-x-auto thin-scroll">
            <table className="w-full text-[13px] min-w-[420px]">
              <tbody>
                {s.measures.map((m) => (
                  <tr key={m.measure} className="border-t border-line">
                    <td className="px-5 py-2 text-ink-2">{cap(m.label)}</td>
                    <td className="px-3 py-2 font-mono text-[11.5px] text-ink-3">{m.values.map((v) => fmt(v)).join(' · ')}</td>
                    <td className="px-5 py-2 tabular text-right whitespace-nowrap">{fmt(m.lowest)} · <span className="font-semibold">{fmt(m.mean)}</span> · {fmt(m.highest)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  )
}

export function RepeatTab({ bp, words, repeatId }) {
  const session = useSession()
  const id = repeatId || session.repeats?.[bp.id] || null
  const { data, error } = useRepeat(id)
  const [times, setTimes] = useState(3)
  const [starting, setStarting] = useState(false)
  const [startErr, setStartErr] = useState(null)

  if (!bp.approved) {
    return <Card><EmptyState icon={<IconLock size={28} className="text-ink-3" />} title="Approve the blueprint first">Repeated runs use exactly the approved values each time.</EmptyState></Card>
  }
  const start = async () => {
    setStarting(true); setStartErr(null)
    try { await startRepeats(bp.id, times, null) } catch (err) { setStartErr(err) } finally { setStarting(false) }
  }
  const running = data?.status === 'running'
  const done = (data?.runs || []).filter((r) => r.status !== 'waiting' && r.status !== 'running').length

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold">Run the same conditions several times</h3>
          <p className="text-[13px] text-ink-2 mt-1 max-w-2xl">One run shows one way the term can go. The AI people choose afresh each time, so running exactly the same blueprint again shows how often each person fails, not just whether they did once.</p>
        </div>
        <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
          <div className="flex items-center gap-1.5" role="radiogroup" aria-label="How many runs">
            {CHOICES.map((n) => (
              <button key={n} type="button" role="radio" aria-checked={times === n} onClick={() => setTimes(n)} disabled={starting || running}
                className={cx('h-8 px-3 rounded-full border text-[12.5px] font-medium', times === n ? 'bg-ink text-white border-ink' : 'bg-white/70 border-white text-ink-2 hover:bg-white')}>{n} runs</button>
            ))}
          </div>
          <Button variant={data ? 'secondary' : 'primary'} icon={<IconRestart size={16} />} onClick={start} disabled={starting || running}>{starting ? 'Starting…' : 'Repeat runs'}</Button>
          <span className="text-[11.5px] text-ink-3">Uses {times} of today's runs and real AI calls; about {times}–{times * 1.5} minutes.</span>
        </div>
      </Card>
      <ApiErrorBanner error={startErr} context={{ limit: "Today's limit for simulations is too low for that many runs. You can still open finished runs." }} />
      {error && !data && <ApiErrorBanner error={error} context={{ notfound: 'No repeated runs with that ID.' }} />}
      {id && !data && !error && <LoadingBlock label="Opening the repeated runs…" />}
      {data && (
        <>
          <WithinModelBanner sub={data.note} />
          <Card className="!p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <IdTag id={data.id} label="Repeat" />
              {running ? <Badge tone="blue"><Dot tone="live" /> Running</Badge> : data.status === 'completed' ? <Badge tone="ok">Finished</Badge> : <Badge tone="bad">{data.status}</Badge>}
              {data.runs.map((r, i) => r.run_id
                ? <a key={r.run_id} href={href(`/run/${r.run_id}`)} className="font-mono text-[11.5px] text-blue-700 hover:underline">{r.run_id}{r.included ? ' (included)' : ''}</a>
                : <span key={i} className="font-mono text-[11.5px] text-ink-3">{r.status}</span>)}
            </div>
            <div className="flex items-center gap-3 sm:w-64">
              <Progress value={done} max={data.runs.length} label="Runs finished" className="flex-1" />
              <span className="text-[12.5px] font-mono tabular shrink-0">{done} / {data.runs.length}</span>
            </div>
          </Card>
          {data.status === 'failed' && <Banner tone="bad" title="The repeated runs stopped with an error">{data.error}</Banner>}
          {data.summary ? <Summary s={data.summary} words={words} /> : running && <LoadingBlock label="The counts appear as each run finishes…" />}
        </>
      )}
    </div>
  )
}
