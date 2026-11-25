// S9b Policy comparison (slice 17): strict, flexible and progressive versions of the approved policy,
// run under the same environment and people, shown as a trade-off table with no score.
// POST /api/comparisons proposes the versions (one AI call, 10-30 s), then GET /api/comparisons/{id}
// is polled while the three runs go one after another.
import { useEffect, useState } from 'react'
import { Badge, Banner, Button, Card, CardTitle, Dot, EmptyState, IdTag, Progress, cx } from '../ui/primitives.jsx'
import { IconLock, IconSplit } from '../ui/icons.jsx'
import { ApiErrorBanner, LoadingBlock, WaitingState } from './feedback.jsx'
import { WithinModelBanner } from './labels.jsx'
import { api } from '../lib/api.js'
import { useElapsed } from '../lib/hooks.js'
import { href, navigate } from '../lib/router.js'
import { setSession, useSession } from '../lib/session.js'
import { cap, formatValue, humanize, pct } from '../lib/words.js'

const VERSION_TEXT = {
  strict: 'The rule to the letter',
  flexible: 'Provisions for disruptions',
  progressive: 'Early warnings and support',
}

function useComparison(id) {
  const [state, setState] = useState({ data: null, error: null })
  useEffect(() => {
    if (!id) { setState({ data: null, error: null }); return }
    let alive = true
    let timer = null
    const tick = async () => {
      try {
        const data = await api.getComparison(id)
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

function cell(v, words) {
  if (v == null) return <span className="text-ink-3">—</span>
  if (Array.isArray(v)) return v.length ? v.map((p) => words.name(p)).join(', ') : <span className="text-ink-3">none</span>
  return <span className="tabular">{String(v)}</span>
}

function VersionHead({ v, words }) {
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[15px] font-semibold">{cap(v.name)}</span>
        {v.run_id && v.status === 'running' ? <Badge tone="blue"><Dot tone="live" /> running</Badge>
          : v.status === 'completed' || v.status === 'degraded' ? <Badge tone="ok">ran</Badge> : <Badge>{v.status}</Badge>}
      </div>
      <p className="text-[12.5px] text-ink-2">{v.approach || VERSION_TEXT[v.name]}</p>
      <div className="rounded-xl bg-mist border border-line p-2.5">
        <div className="eyebrow !text-[10px] mb-1">What it changed</div>
        {v.changed?.length ? (
          <ul className="flex flex-col gap-1 text-[12px]">
            {v.changed.map((c) => {
              const p = words.param(c.parameter)
              const text = p?.type === 'text'
              return (
                <li key={c.parameter}>
                  <span className="text-ink-2">{cap(p?.description || humanize(c.parameter))}:</span>{' '}
                  {text ? <span className="italic">“{c.to}”</span>
                    : <span className="font-semibold tabular">{formatValue(c.from, p)} → {formatValue(c.to, p)}</span>}
                </li>
              )
            })}
          </ul>
        ) : <span className="text-[12px] text-ink-3">Nothing: the policy as approved.</span>}
      </div>
      {v.run_id && <a className="text-[12px] font-mono text-blue-700 hover:underline" href={href(`/run/${v.run_id}`)}>run {v.run_id} →</a>}
      {v.errors?.length > 0 && <span className="text-[12px] text-bad">{v.errors.join('; ')}</span>}
    </div>
  )
}

function Table({ data, words }) {
  const t = data.table
  const cols = t.columns
  const flips = (row) => new Set(cols.map((c) => row[c]?.passed)).size > 1
  return (
    <>
      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto thin-scroll">
          <table className="w-full text-[13px] min-w-[520px]">
            <caption className="sr-only">Trade-offs per policy version</caption>
            <thead>
              <tr className="text-left text-ink-3 text-[12px]">
                <th className="px-4 py-3 font-medium">Measure</th>
                {cols.map((c) => <th key={c} className="px-4 py-3 font-medium">{cap(c)}</th>)}
              </tr>
            </thead>
            <tbody>
              {t.rows.map((r) => (
                <tr key={r.measure} className="border-t border-line">
                  <td className="px-4 py-2.5 text-ink-2">{cap(r.label)}</td>
                  {cols.map((c) => <td key={c} className="px-4 py-2.5">{cell(r[c], words)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {t.checks.length > 0 && (
        <Card className="!p-0 overflow-hidden">
          <div className="px-4 pt-4"><CardTitle className="!mb-3" title="Check results per person" sub="Rows where the result differs between versions are marked" /></div>
          <div className="overflow-x-auto thin-scroll">
            <table className="w-full text-[13px] min-w-[520px]">
              <thead>
                <tr className="text-left text-ink-3 text-[12px]">
                  <th className="px-4 py-2 font-medium">Person</th>
                  {cols.map((c) => <th key={c} className="px-4 py-2 font-medium">{cap(c)}</th>)}
                </tr>
              </thead>
              <tbody>
                {t.checks.map((row) => (
                  <tr key={row.person} className={cx('border-t border-line', flips(row) && 'bg-orange-50/60')}>
                    <td className="px-4 py-2.5">
                      <span className="font-medium">{words.name(row.person)}</span>
                      {flips(row) && <Badge tone="orange" className="ml-2 !h-5 !text-[11px]">differs</Badge>}
                    </td>
                    {cols.map((c) => {
                      const x = row[c]
                      if (!x) return <td key={c} className="px-4 py-2.5 text-ink-3">not checked</td>
                      return (
                        <td key={c} className="px-4 py-2.5">
                          <span className="inline-flex items-center gap-2">
                            <span className={cx('w-2 h-2 rounded-full', x.passed ? 'bg-ok' : 'bg-bad')} />
                            <span className="tabular font-medium">{x.value == null ? '—' : pct(x.value)}</span>
                            <span className="text-ink-3">{words.outcome(x.passed)}</span>
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  )
}

export function ComparisonTab({ bp, words, comparisonId }) {
  const session = useSession()
  const id = comparisonId || session.comparisons?.[bp.id] || null
  const { data, error } = useComparison(id)
  const [starting, setStarting] = useState(false)
  const [startErr, setStartErr] = useState(null)
  const seconds = useElapsed(starting)

  if (!bp.approved) {
    return <Card><EmptyState icon={<IconLock size={28} className="text-ink-3" />} title="Approve the blueprint first">The comparison rewrites an approved policy three ways and runs each under the same conditions and people.</EmptyState></Card>
  }
  const start = async () => {
    setStarting(true); setStartErr(null)
    try {
      const c = await api.startComparison(bp.id)
      setSession((st) => ({ comparisons: { ...(st.comparisons || {}), [bp.id]: c.id } }))
      navigate(`/blueprint/${bp.id}/compare/${c.id}`)
    } catch (err) { setStartErr(err) } finally { setStarting(false) }
  }
  const running = data?.status === 'running'
  const done = (data?.versions || []).filter((v) => v.status !== 'waiting' && v.status !== 'running').length
  const other = startErr?.body?.comparison_id

  if (starting) {
    return <WaitingState seconds={seconds} title="Writing three versions of the policy" sentence="The AI is rewriting the policy as strict, flexible and progressive versions with the same goal. This takes about 10–30 seconds; then the three runs start." />
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold">Compare strict, flexible and progressive versions</h3>
          <p className="text-[13px] text-ink-2 mt-1 max-w-2xl">The AI rewrites how the policy is applied three ways: to the letter, with provisions for disruptions, and with early warnings and support. Values you stated stay the same in all three. Each runs under the same conditions and people. There is no winner: you weigh the trade-offs.</p>
        </div>
        <div className="flex flex-col items-start md:items-end gap-1.5 shrink-0">
          <Button variant={data ? 'secondary' : 'primary'} icon={<IconSplit size={16} />} onClick={start} disabled={running}>{data ? 'Compare again' : 'Compare policies'}</Button>
          <span className="text-[11.5px] text-ink-3">Uses 3 of today's runs and real AI calls; about 2–3 minutes.</span>
        </div>
      </Card>

      {other
        ? <Banner tone="bad" title="Another comparison or search is running right now.">Only one comparison, search or run goes at a time, for everyone. Try again when it finishes.</Banner>
        : <ApiErrorBanner error={startErr} context={{ limit: "Today's limit for simulations is too low for a comparison (it needs 3 runs). You can still open finished runs." }} />}
      {error && !data && <ApiErrorBanner error={error} context={{ notfound: 'No comparison with that ID.' }} />}
      {id && !data && !error && <LoadingBlock label="Opening the comparison…" />}

      {data && (
        <>
          <WithinModelBanner sub="All three versions are simulations of the same model under the same conditions and people. The differences are evidence about the model, not proof about a real college." />
          <Card className="!p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <IdTag id={data.id} label="Comparison" />
              {running ? <Badge tone="blue"><Dot tone="live" /> Running the versions</Badge>
                : data.status === 'completed' ? <Badge tone="ok">Finished</Badge> : <Badge tone="bad">{data.status}</Badge>}
              {data.matched?.same_environment_and_people && <Badge>same conditions and people</Badge>}
            </div>
            <div className="flex items-center gap-3 sm:w-72">
              <Progress value={done} max={data.versions.length || 3} label="Versions run" className="flex-1" />
              <span className="text-[12.5px] font-mono tabular shrink-0">{done} / {data.versions.length || 3} runs</span>
            </div>
          </Card>
          {data.status === 'invalid' && <Banner tone="bad" title="The AI's versions didn't pass the checks">{(data.errors || []).join('; ') || 'Try again.'}</Banner>}
          {data.status === 'failed' && <Banner tone="bad" title="The comparison stopped with an error">{data.error}</Banner>}
          {data.kept?.length > 0 && (
            <Banner tone="blue" title="Kept the same in every version, as you stated them">
              {data.kept.map((k) => `${cap(words.param(k.parameter)?.description || humanize(k.parameter))}: ${formatValue(k.value, words.param(k.parameter))}`).join(' · ')}
            </Banner>
          )}
          <div className="grid md:grid-cols-3 gap-3">
            {data.versions.map((v) => <Card key={v.name} className="!p-4"><VersionHead v={v} words={words} /></Card>)}
          </div>
          {data.table ? <Table data={data} words={words} /> : running && <LoadingBlock label="The table appears as each version's run finishes…" />}
          <Banner tone="orange" title="Read this before deciding">{data.note}</Banner>
          {!running && data.table && (
            <Card className="flex flex-col gap-2">
              <h3 className="text-[16px] font-semibold">You decide</h3>
              <p className="text-[13px] text-ink-2">{data.no_overall_score} Open each version's run to see its findings and the evidence behind them.</p>
              <div className="flex flex-wrap gap-2">
                {data.versions.filter((v) => v.run_id).map((v) => (
                  <a key={v.name} className="text-[13px] text-blue-700 hover:underline" href={href(`/run/${v.run_id}/analysis/findings`)}>Findings of {v.name} ({v.run_id})</a>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
