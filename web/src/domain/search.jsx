// S4b Guided search (slice 16b): start a search for the conditions that break an approved policy,
// then follow it round by round: what each scenario changed, how close each run came, and the
// confirmed break (with its evidence) or the closest scenario. Polls GET /api/searches/{id}.
import { useEffect, useState } from 'react'
import { Badge, Banner, Button, Card, CardTitle, Dot, EmptyState, IdTag, Progress, cx } from '../ui/primitives.jsx'
import { IconArrow, IconLock, IconSearch } from '../ui/icons.jsx'
import { ApiErrorBanner, LoadingBlock } from './feedback.jsx'
import { WithinModelBanner } from './labels.jsx'
import { api } from '../lib/api.js'
import { href, navigate } from '../lib/router.js'
import { setSession, useSession } from '../lib/session.js'
import { cap, humanize } from '../lib/words.js'

const RUN_CHOICES = [3, 6, 9]

/** How close a run came: 0 or fewer misses to spare = reached; more to spare = further away. */
function nearness(c) {
  const spare = c?.closest?.spare
  if (spare == null) return { pct: 5, tone: 'blue', label: 'nowhere near a check' }
  if (spare <= 0) return { pct: 100, tone: 'bad', label: 'reached the check' }
  return { pct: Math.max(8, Math.round(100 / (1 + spare))), tone: spare <= 2 ? 'orange' : 'blue',
    label: `${spare} to spare` }
}

function Nearness({ c }) {
  const n = nearness(c)
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="h-1.5 w-20 shrink-0 rounded-full bg-white border border-line overflow-hidden" aria-hidden>
        <div className={cx('h-full rounded-full', n.tone === 'bad' ? 'bg-bad' : n.tone === 'orange' ? 'bg-orange-500' : 'bg-blue-600')} style={{ width: `${n.pct}%` }} />
      </div>
      <span className="text-[12px] text-ink-2 min-w-0">{c?.closest?.text || n.label}</span>
    </div>
  )
}

function Changed({ list, words }) {
  if (!list?.length) return <span className="text-[12.5px] text-ink-3">No condition differs.</span>
  return (
    <ul className="flex flex-col gap-1 text-[12.5px]">
      {list.map((c) => {
        const p = words.param(c.parameter)
        const name = cap(p?.description || humanize(c.parameter))
        if (c.added || c.removed) {
          return (
            <li key={c.parameter}>
              <span className="text-ink-2">{name}:</span>
              <ul className="mt-0.5 pl-3">
                {(c.added || []).map((d, i) => <li key={`a${i}`}>+ {d}</li>)}
                {(c.removed || []).map((d, i) => <li key={`r${i}`} className="text-ink-3"><span aria-label="removed">− </span><span className="line-through">{d}</span></li>)}
              </ul>
            </li>
          )
        }
        return <li key={c.parameter}><span className="text-ink-2">{name}:</span> <span className="font-semibold tabular">{String(c.from)} → {String(c.to)}</span></li>
      })}
    </ul>
  )
}

function scenarioTone(status) {
  if (status?.startsWith('broke, repeated')) return 'bad'
  if (status?.startsWith('broke once')) return 'orange'
  if (status === 'running') return 'blue'
  return 'neutral'
}

function Scenario({ s, words }) {
  return (
    <Card className="!p-4 flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        {s.source === 'random' ? <Badge>Random, no AI</Badge> : <Badge tone="blue">Targeted by the AI</Badge>}
        <Badge tone={scenarioTone(s.status)}>{s.runs?.some((r) => r.status === 'running') ? <><Dot tone="live" /> running</> : s.status}</Badge>
      </div>
      <div className="min-w-0">
        <h4 className="text-[14.5px] font-semibold">{s.name}</h4>
        <p className="text-[12.5px] text-ink-2 mt-0.5">{s.weak_point}</p>
      </div>
      <div className="rounded-xl bg-mist border border-line p-3">
        <div className="eyebrow !text-[10px] mb-1.5">What changed</div>
        <Changed list={s.changed} words={words} />
      </div>
      {s.runs?.length > 0 && (
        <ul className="flex flex-col gap-2">
          {s.runs.map((r, i) => (
            <li key={r.run_id || i} className="flex flex-col gap-1.5 rounded-xl bg-white/70 border border-white px-3 py-2">
              <div className="flex items-center gap-2 flex-wrap text-[12px]">
                <span className="text-ink-3">{i === 0 ? 'Run' : 'Rerun'}</span>
                {r.run_id ? <a className="font-mono text-blue-700 hover:underline" href={href(`/run/${r.run_id}`)}>{r.run_id}</a> : <span className="text-ink-3">waiting for the slot</span>}
                {r.status !== 'running' && r.run_id && (r.findings?.length
                  ? <Badge tone="bad" className="!h-5 !text-[11px]">{r.findings.length} finding{r.findings.length > 1 ? 's' : ''}</Badge>
                  : <Badge className="!h-5 !text-[11px]">no finding</Badge>)}
              </div>
              {r.closeness && <Nearness c={r.closeness} />}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Result({ s, words }) {
  if (s.status === 'running') return null
  if (s.status === 'failed') return <Banner tone="bad" title="The search stopped with an error">{s.error}</Banner>
  const r = s.result || {}
  if (s.status === 'broken') {
    const runs = r.runs || []
    return (
      <section className="accent-card relative overflow-hidden rounded-[var(--radius-card)] p-5 flex flex-col gap-3">
        <div className="text-[12px] font-medium text-ink/70">Confirmed break · found by rules from the records</div>
        <h3 className="text-[20px] font-semibold leading-snug">The policy breaks under “{r.scenario}”</h3>
        <p className="text-[13.5px]">{r.closeness}. The rerun on the same conditions broke it again.</p>
        <div className="flex flex-wrap gap-2">
          {runs.map((id) => <IdTag key={id} id={id} label="Run" />)}
        </div>
        <div className="flex flex-wrap gap-2">
          {(r.findings || []).slice(0, 4).map((fid) => {
            const run = fid.split('-F')[0]
            return <Button key={fid} size="sm" variant="primary" iconRight={<IconArrow size={14} />} onClick={() => navigate(`/run/${run}/analysis/evidence/${fid}`)}>Evidence {fid}</Button>
          })}
        </div>
      </section>
    )
  }
  return (
    <Card className="!p-5 flex flex-col gap-2">
      <div className="eyebrow !text-[10px]">No confirmed break</div>
      <h3 className="text-[18px] font-semibold">The policy held: {r.summary}</h3>
      {r.closest && <p className="text-[13.5px] text-ink-2">Closest: “{r.closest.scenario}” ({r.closest.source}): {r.closest.closeness}.</p>}
      {r.stopped && <p className="text-[12.5px] text-ink-3">Stopped early: {r.stopped}</p>}
      <p className="text-[12.5px] text-ink-3">The search never invents a break. Run another search for more rounds, or try a what-if on the closest run.</p>
    </Card>
  )
}

function useSearch(id) {
  const [state, setState] = useState({ data: null, error: null })
  useEffect(() => {
    if (!id) { setState({ data: null, error: null }); return }
    let alive = true
    let timer = null
    const tick = async () => {
      try {
        const data = await api.getSearch(id)
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

export function SearchTab({ bp, words, searchId }) {
  const session = useSession()
  const id = searchId || session.searches?.[bp.id] || null
  const { data, error } = useSearch(id)
  const [maxRuns, setMaxRuns] = useState(6)
  const [starting, setStarting] = useState(false)
  const [startErr, setStartErr] = useState(null)

  if (!bp.approved) {
    return <Card><EmptyState icon={<IconLock size={28} className="text-ink-3" />} title="Approve the blueprint first">The search tries harsher conditions on an approved blueprint. The policy and the people stay the same.</EmptyState></Card>
  }
  const start = async () => {
    setStarting(true); setStartErr(null)
    try {
      const s = await api.startSearch(bp.id, maxRuns)
      setSession((st) => ({ searches: { ...(st.searches || {}), [bp.id]: s.id } }))
      navigate(`/blueprint/${bp.id}/search/${s.id}`)
    } catch (err) { setStartErr(err) } finally { setStarting(false) }
  }
  const otherSearch = startErr?.body?.search_id
  const running = data?.status === 'running'

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold">Search for the conditions that break this policy</h3>
          <p className="text-[13px] text-ink-2 mt-1 max-w-2xl">Each round runs 2 scenarios aimed by the AI and 1 drawn at random, so it also looks where the AI wouldn't. From round 2 the AI is told how close the last runs came and pushes that weak point. A break counts only if a rerun repeats it. Only the conditions change; the policy and the people stay as approved.</p>
        </div>
        <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
          <div className="flex items-center gap-1.5" role="radiogroup" aria-label="Runs the search may use">
            <span className="text-[12px] text-ink-3 mr-1">Up to</span>
            {RUN_CHOICES.map((n) => (
              <button key={n} type="button" role="radio" aria-checked={maxRuns === n} onClick={() => setMaxRuns(n)} disabled={starting || running}
                className={cx('h-8 px-3 rounded-full border text-[12.5px] font-medium', maxRuns === n ? 'bg-ink text-white border-ink' : 'bg-white/70 border-white text-ink-2 hover:bg-white')}>{n} runs</button>
            ))}
          </div>
          <Button variant={data ? 'secondary' : 'primary'} icon={<IconSearch size={16} />} onClick={start} disabled={starting || running}>
            {starting ? 'Starting…' : data ? 'Start a new search' : 'Search for breaking conditions'}
          </Button>
          <span className="text-[11.5px] text-ink-3">Uses up to {maxRuns} of today's runs and real AI calls; about {Math.round(maxRuns * 0.8)}–{maxRuns * 1.5} minutes.</span>
        </div>
      </Card>

      {otherSearch
        ? <Banner tone="bad" title="Another search is running right now." action={<Button size="sm" variant="primary" onClick={() => navigate(`/blueprint/${bp.id}/search/${otherSearch}`)}>Watch it</Button>}>Only one search, comparison or run goes at a time, for everyone.</Banner>
        : <ApiErrorBanner error={startErr} context={{ limit: "Today's limit for simulations is too low for a search. You can still open finished runs and searches." }} />}
      {error && !data && <ApiErrorBanner error={error} context={{ notfound: 'No search with that ID.' }} />}
      {id && !data && !error && <LoadingBlock label="Opening the search…" />}

      {data && (
        <>
          <WithinModelBanner sub="Every scenario is a simulation of the same model. A break is evidence about the model, not proof about a real college. The AI people choose afresh in each run, which is why a break must repeat." />
          <Card className="!p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <IdTag id={data.id} label="Search" />
              {running ? <Badge tone="blue"><Dot tone="live" /> Searching</Badge>
                : data.status === 'broken' ? <Badge tone="bad">Broken, confirmed</Badge>
                  : data.status === 'not_broken' ? <Badge tone="ok">Held</Badge> : <Badge tone="bad">{data.status}</Badge>}
              <span className="text-[12.5px] text-ink-3">round {data.rounds.length || 1}</span>
            </div>
            <div className="flex items-center gap-3 sm:w-72">
              <Progress value={data.runs_used} max={data.max_runs} tone={running ? 'blue' : 'orange'} label="Runs used" className="flex-1" />
              <span className="text-[12.5px] font-mono tabular shrink-0">{data.runs_used} / {data.max_runs} runs</span>
            </div>
          </Card>
          <Result s={data} words={words} />
          {data.rounds.map((r) => (
            <section key={r.round} className="flex flex-col gap-3">
              <CardTitle className="!mb-0" title={`Round ${r.round}`}
                sub={r.pushes ? `Pushes the closest so far: ${r.pushes}` : 'First round: aimed at the weak points the engine works out from the approved values.'} />
              {r.proposal_error && <Banner tone="orange" title="The AI's proposal failed this round, so only the random scenario ran">{r.proposal_error}</Banner>}
              <div className="grid lg:grid-cols-3 gap-3">
                {r.scenarios.map((s) => <Scenario key={s.blueprint_id || s.name} s={s} words={words} />)}
              </div>
            </section>
          ))}
          {running && data.rounds.length === 0 && <LoadingBlock label="The AI is aiming the first round…" />}
        </>
      )}
    </div>
  )
}
