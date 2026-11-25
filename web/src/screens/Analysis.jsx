// S6–S9 Analysis: Summary · Findings · Evidence (the hero) · What if? · Compare, as tabs.
import { useEffect, useMemo, useState } from 'react'
import { Badge, Banner, Button, Card, CardTitle, EmptyState, IdTag, Progress, StatTile, Tabs, cx } from '../ui/primitives.jsx'
import { IconArrow, IconBack, IconBolt, IconSearch, IconSplit } from '../ui/icons.jsx'
import { PageHeader } from '../ui/shell.jsx'
import { ApiErrorBanner, LoadingBlock } from '../domain/feedback.jsx'
import { StatusBadge, WithinModelBanner } from '../domain/labels.jsx'
import { CalcPanel, EvidenceTimeline, FindingCard, HeroFinding, MissChart } from '../domain/analysis.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import TimeRuler from '../sim/TimeRuler.jsx'
import { api, ApiError } from '../lib/api.js'
import { templateIdOf, useAdaptations, useBlueprint, useEvidence, useFindings, useLoad, useRun, useTemplate } from '../lib/hooks.js'
import { AdaptationList } from '../domain/adaptation.jsx'
import { PersonPanel } from '../domain/personPanel.jsx'
import { startRepeats } from '../domain/repeats.jsx'
import { navigate } from '../lib/router.js'
import { rememberRun, rememberWhatIf, useSession } from '../lib/session.js'
import { cap, formatValue, humanize, makeWords, pct } from '../lib/words.js'

const TABS = ['summary', 'findings', 'evidence', 'whatif', 'compare']

function lastChecks(events) {
  const out = {}
  for (const e of events) if (e.type === 'check_evaluated') out[e.payload.person] = e
  return out
}

function checkText(e, words) {
  if (!e) return null
  const p = e.payload
  const ladder = p.ladder_steps != null
  const passed = ladder ? !p.outcome : p.passed
  const value = p.count?.kind === 'rate' ? pct(p.count.value) : p.count?.value
  return { passed, value, outcome: ladder ? (p.outcome || p.standing || 'no step') : words.outcome(p.passed), period: e.period }
}

/* ------------------------------------------------------------------ Summary */
function Summary({ run, events, words, findings, onEvidence, blueprint }) {
  const adapt = useAdaptations(run.run_id, run.status)
  const [panel, setPanel] = useState(null) // slice 20
  const s = run.summary || {}
  const filed = events.filter((e) => e.type === 'request_filed').length
  const checks = lastChecks(events)
  const reasons = {}
  for (const e of events) if (e.type === 'decision' && e.payload?.reason) reasons[e.actor] = e.payload.reason
  const refused = {}
  for (const r of s.rejected || []) refused[r.agent] = (refused[r.agent] || 0) + 1
  const hero = findings?.[0]
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="AI decisions" value={s.decisions ?? '—'} sub={`${s.no_actions || 0} chose to do nothing`} />
        <StatTile label="Model calls" value={s.llm_calls ?? '—'} sub={`${s.llm_errors || 0} errors · cap ${s.llm_cap ?? '—'}`} tone={s.llm_errors ? 'bad' : undefined} />
        <StatTile label="Refused actions" value={(s.rejected || []).length} sub="blocked by the rule engine" />
        <StatTile label={`${cap(words.terms.requests)} filed`} value={filed} sub={`${findings?.length ?? 0} finding${findings?.length === 1 ? '' : 's'}`} tone={findings?.length ? 'bad' : 'ok'} />
      </div>
      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-4">
        {hero ? <HeroFinding f={hero} words={words} check={events.find((e) => e.event_id === hero.check_event_id)?.payload} onOpen={() => onEvidence(hero.finding_id)} /> : (
          <section className="glass rounded-[var(--radius-card)] p-6 flex flex-col min-h-[300px]">
            <div className="flex items-center gap-2 text-[12px] font-medium text-ink-2"><span className="w-2 h-2 rounded-full bg-ok" /> Found by rules from the records</div>
            <div className="mt-auto pt-10 text-[30px] font-normal tracking-[-0.02em] leading-tight">No problems found in this run.</div>
            <p className="mt-2 text-[14px] text-ink-2">Nobody failed a check and no request was left waiting at one. Try harsher conditions to look for weak points.</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button onClick={() => navigate(`/blueprint/${run.blueprint_id}/stress`)} icon={<IconBolt size={16} />}>Stress-test the policy</Button>
              <Button onClick={() => navigate(`/run/${run.run_id}/analysis/whatif`)}>What if?</Button>
            </div>
          </section>
        )}
        <Card>
          <CardTitle title={`${cap(words.terms.missed_plural || 'misses')} recorded by ${words.period}`} sub="Counted from this run's own records, corrections applied" />
          <MissChart events={events} words={words} highlight={hero?.person} />
        </Card>
      </div>
      <Card>
        <CardTitle title="How each person ended the term" sub="The check result, how often they decided, and their last stated reason. Click a name to see everything about them." />
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-[13px] min-w-[640px]">
            <thead><tr className="text-left text-ink-3 text-[12px]">
              <th className="font-medium px-2 py-2">Person</th><th className="font-medium px-2 py-2">{cap(words.template.checks?.[0]?.label || 'Check')}</th>
              <th className="font-medium px-2 py-2">Decisions</th><th className="font-medium px-2 py-2">Refused</th><th className="font-medium px-2 py-2">Last stated reason</th>
            </tr></thead>
            <tbody>
              {words.travellers.map((id) => {
                const c = checkText(checks[id], words)
                return (
                  <tr key={id} className="border-t border-line align-top">
                    <td className="px-2 py-3"><button type="button" onClick={() => setPanel(id)} className="flex items-center gap-2.5 text-left rounded-xl hover:bg-white/60 pr-2" aria-label={`Everything about ${words.name(id)}`}><PersonAvatar colour={words.colour(id)} size={30} mood={c && !c.passed ? 'sad' : 'idle'} /><div><div className="font-medium text-blue-700 underline-offset-2 hover:underline">{words.name(id)}</div><div className="text-[12px] text-ink-3">{words.label(id)}</div></div></button></td>
                    <td className="px-2 py-3">{c ? <span className="inline-flex items-center gap-2"><span className={cx('w-2 h-2 rounded-full', c.passed ? 'bg-ok' : 'bg-bad')} /><span className="tabular font-medium">{c.value}</span><span className="text-ink-3">{c.outcome} · {words.period} {c.period}</span></span> : <span className="text-ink-3">not checked</span>}</td>
                    <td className="px-2 py-3 tabular">{s.decisions_by_agent?.[id] ?? 0}</td>
                    <td className="px-2 py-3 tabular">{refused[id] || 0}</td>
                    <td className="px-2 py-3 text-ink-2 italic max-w-md">{reasons[id] ? `“${reasons[id]}”` : <span className="not-italic text-ink-3">no decision</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <RunAgain run={run} />
      <Card>
        <CardTitle title="How people adapted" sub="Found by rules over this run's records, no AI: a change to their own value and what it changed later, things they did for the first time, and changes in their stated strategy (their own words)" />
        {adapt.loading ? <LoadingBlock label="Reading the records…" />
          : adapt.error ? <ApiErrorBanner error={adapt.error} onRetry={adapt.reload} />
            : <AdaptationList items={adapt.data?.adaptations} words={words} />}
      </Card>
      {panel && (
        <PersonPanel id={panel} events={events} words={words} blueprint={blueprint} adaptations={adapt.data?.adaptations}
          onClose={() => setPanel(null)} onJump={(eventId) => navigate(`/run/${run.run_id}?at=${eventId}`)} />
      )}
    </div>
  )
}

/** Slice 21: one run is one way the term can go; run the same blueprint again and count how often. */
function RunAgain({ run }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  if (run.status !== 'completed' && run.status !== 'degraded') return null
  const go = async () => {
    setBusy(true); setError(null)
    try { await startRepeats(run.blueprint_id, 2, run.run_id) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <Card className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold">Is this one run's luck?</h3>
        <p className="text-[13px] text-ink-2 mt-0.5">Run exactly the same conditions 2 more times and count how often each person fails. Uses 2 of today's runs.</p>
        <ApiErrorBanner error={error} className="mt-2" context={{ limit: "Today's limit for simulations is reached." }} />
      </div>
      <Button onClick={go} disabled={busy} icon={<IconBolt size={16} />}>{busy ? 'Starting…' : 'Run it again'}</Button>
    </Card>
  )
}

/* ----------------------------------------------------------------- Findings */
function Findings({ run, events, words, findings, onEvidence }) {
  if (!findings.length) {
    return <Card><EmptyState title="No problems found in this run." action={<><Button variant="primary" icon={<IconBolt size={16} />} onClick={() => navigate(`/blueprint/${run.blueprint_id}/stress`)}>Stress-test the policy</Button><Button onClick={() => navigate(`/run/${run.run_id}/analysis/whatif`)}>What if?</Button></>}>Findings come only from rules over this run's records. None of them fired.</EmptyState></Card>
  }
  const byId = Object.fromEntries(events.map((e) => [e.event_id, e]))
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13.5px] text-ink-2">Found by rules from the records, not written by an AI. Each one links to the exact events behind it.</p>
      <div className="grid lg:grid-cols-2 gap-4">
        {findings.map((f) => <FindingCard key={f.finding_id} f={f} words={words} check={byId[f.check_event_id]?.payload} onOpen={() => onEvidence(f.finding_id)} />)}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- Evidence */
function Evidence({ run, events, words, findings, fid }) {
  const ev = useEvidence(fid)
  const [focus, setFocus] = useState(null)
  const f = findings.find((x) => x.finding_id === fid)
  if (!findings.length) return <Card><EmptyState title="No findings, so no evidence to show.">This run had no failed checks and no requests waiting at a check.</EmptyState></Card>
  if (ev.loading) return <LoadingBlock label="Tracing the evidence…" />
  if (ev.error) return <ApiErrorBanner error={ev.error} onRetry={ev.reload} context={{ notfound: 'No finding with that ID.' }} />
  if (!ev.data || !f) return null
  const steps = ev.data.steps || []
  const calc = steps.find((s) => s.calculation)?.calculation
  const check = events.find((e) => e.event_id === f.check_event_id)?.payload
  const per = {}
  const dis = {}
  for (const s of steps) {
    per[s.period] = (per[s.period] || 0) + 1
    if (['obstacle', 'capacity_changed', 'occurrence_cancelled'].includes(s.type)) dis[s.period] = (dis[s.period] || 0) + 1
  }
  const periods = [...new Set(steps.map((s) => s.period))]
  const reasons = steps.filter((s) => s.label === 'AI interpretation').length
  const disruptions = steps.filter((s) => s.type === 'obstacle' || s.type === 'capacity_changed')
  const counts = { fact: steps.filter((s) => s.label === 'recorded fact').length, calc: steps.filter((s) => s.label === 'calculated').length }
  return (
    <div className="flex flex-col gap-4">
      {findings.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] text-ink-3 mr-1">Finding</span>
          <Tabs size="sm" value={fid} onChange={(id) => navigate(`/run/${run.run_id}/analysis/evidence/${id}`)}
            tabs={findings.map((x) => ({ id: x.finding_id, label: `${words.name(x.person)} · ${x.kind === 'check_failed' ? 'failure' : 'bottleneck'}` }))} />
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="Linked events" value={steps.length} sub={periods.length > 1 ? `${cap(words.period)} ${periods[0]} to ${periods[periods.length - 1]}` : `${cap(words.period)} ${periods[0]}`} />
        <StatTile label="Disruptions" value={disruptions.length} sub={[...new Set(disruptions.map((d) => d.text.split(':')[0]))].join(' · ') || 'none in the chain'} />
        <StatTile label="Stated reasons" value={reasons} sub="AI interpretations, quoted as said" />
        <StatTile label={`${cap(words.terms.requests)} waiting`} value={f.pending_requests.length} sub={f.pending_requests.length ? f.pending_requests.join(', ') : 'none were waiting at the check'} tone={f.pending_requests.length ? 'bad' : undefined} />
      </div>
      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-4">
        <HeroFinding f={f} words={words} check={check} />
        <CalcPanel calc={calc} words={words} />
      </div>
      <Card>
        <CardTitle title="How it happened" sub={`${steps.length} events in run order, from the first disruption to the check: ${counts.fact} recorded facts, ${counts.calc} calculations, ${reasons} stated reasons`}
          action={<IdTag id={ev.data.finding_id} label="Finding" />} />
        <div className="flex flex-col md:flex-row md:items-end gap-4 md:gap-8 mb-8">
          <div className="flex-1 min-w-0">
            <TimeRuler periods={run.periods || words.periods} stepsPerPeriod={words.cal.steps_per_period} highlights={per} disruptions={dis} checkpoint={f.period} label={words.period} stepLabel={words.step} onSeek={(p) => setFocus(p)} />
          </div>
          <EvidenceKey />
        </div>
        <EvidenceTimeline steps={steps} words={words} focus={focus} onFocus={setFocus} />
      </Card>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <Button icon={<IconBack size={16} />} onClick={() => navigate(`/run/${run.run_id}/analysis/findings`)}>Back to findings</Button>
        <div className="flex flex-col sm:items-end gap-1">
          <Button variant="primary" size="lg" iconRight={<IconArrow size={18} />} onClick={() => navigate(`/run/${run.run_id}/analysis/whatif`)}>What if?</Button>
          <span className="text-[12px] text-ink-3">Reruns the same term with one condition changed, then compares.</span>
        </div>
      </div>
    </div>
  )
}

function EvidenceKey() {
  return (
    <ul className="flex flex-col gap-1.5 text-[12.5px] shrink-0" aria-label="What the labels mean">
      <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-blue-600" /><span className="text-blue-700">recorded fact</span><span className="text-ink-3">what the engine recorded</span></li>
      <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-[3px] bg-ink" /><span className="font-mono text-ink-2">calculated</span><span className="text-ink-3">what a rule worked out</span></li>
      <li className="flex items-center gap-2"><span className="w-3 h-3 rounded-full border-2 border-orange-500" /><span className="italic text-orange-700">AI interpretation</span><span className="text-ink-3">a person's own stated reason</span></li>
    </ul>
  )
}

/* ------------------------------------------------------------------ What if */
function WhatIf({ run, words, bp }) {
  const s = useSession()
  const names = words.template.counterfactual_parameters || []
  const params = names.map((n) => words.param(n)).filter(Boolean)
  const values = bp?.blueprint?.values || {}
  const [name, setName] = useState(params[0]?.name || '')
  const param = params.find((p) => p.name === name)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [newId, setNewId] = useState(null)
  const live = useRun(newId)
  useEffect(() => { if (param) setValue(String(values[param.name] ?? param.min ?? '')) }, [name, bp]) // eslint-disable-line react-hooks/exhaustive-deps
  const done = live.run && live.run.status !== 'running'
  useEffect(() => { if (done && live.run.status !== 'failed') navigate(`/run/${run.run_id}/analysis/compare/${newId}`) }, [done]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!params.length) return <Card><EmptyState title="No condition can be changed for this template." /></Card>
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    let v = value
    if (param.type === 'int') v = Number(value)
    if (param.type === 'bool') v = value === 'true'
    try {
      const r = await api.counterfactual(run.run_id, param.name, v)
      rememberWhatIf(run.run_id, r.run_id)
      setNewId(r.run_id)
    } catch (err) { setError(err) } finally { setBusy(false) }
  }
  const earlier = (s.whatIfs?.[run.run_id] || []).filter((x) => x !== newId)
  const outOfRange = param.type === 'int' && (value === '' || Number(value) < param.min || Number(value) > param.max)

  return (
    <div className="grid lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-4 items-start">
      <Card>
        <CardTitle title="Rerun the same term with one condition changed" />
        <p className="text-[13.5px] text-ink-2 -mt-2 mb-5">Same people, same disruptions, same policy. Only this one condition changes. The AI people still make their own choices, so some differences come from them.</p>
        {newId ? (
          <div className="flex flex-col gap-4" aria-live="polite">
            <div className="flex items-center gap-2 flex-wrap"><span className="text-[13.5px] font-medium">What-if run</span><IdTag id={newId} label="Run" />{live.run && <StatusBadge status={live.run.status} />}</div>
            <div className="text-[13px] text-ink-2">{cap(words.period)} {live.run?.period || 0} of {live.run?.periods || words.periods}</div>
            <Progress value={live.run?.period || 0} max={live.run?.periods || words.periods} label="What-if progress" />
            {live.run?.status === 'failed' && <Banner tone="bad" title="The what-if run failed">{live.run.error}</Banner>}
            {live.pollError && <Banner tone="orange" title="Lost contact with the server">Trying again every 3 seconds.</Banner>}
            <div className="flex gap-2"><Button onClick={() => navigate(`/run/${newId}`)}>Watch it on the map</Button>{done && <Button variant="primary" onClick={() => navigate(`/run/${run.run_id}/analysis/compare/${newId}`)}>Compare the two runs</Button>}</div>
            <p className="text-[12.5px] text-ink-3">A term takes 30–60 seconds. The comparison opens when it ends.</p>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-5">
            <fieldset>
              <legend className="text-[13.5px] font-medium mb-2">Condition</legend>
              <div className="grid gap-2">
                {params.map((p) => (
                  <label key={p.name} className={cx('flex gap-3 items-start rounded-2xl border px-4 py-3 cursor-pointer transition', name === p.name ? 'bg-white border-blue-200 shadow-[var(--shadow-glass)]' : 'bg-white/50 border-white hover:bg-white')}>
                    <input type="radio" name="cf-param" value={p.name} checked={name === p.name} onChange={() => setName(p.name)} className="mt-1 accent-[var(--color-blue-600)]" />
                    <span className="flex-1"><span className="block text-[13.5px]">{cap(p.description || humanize(p.name))}</span><span className="block font-mono text-[11px] text-ink-3 mt-0.5">{p.name}</span></span>
                    <span className="text-[13px] text-ink-2 shrink-0">in this run: <span className="font-semibold text-ink tabular">{formatValue(values[p.name], p)}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
            {param && (
              <div>
                <label htmlFor="cf-value" className="text-[13.5px] font-medium">New value</label>
                {param.type === 'int' && <p className="text-[12.5px] text-ink-3 mb-2">A whole number from {param.min} to {param.max}.</p>}
                {param.type === 'bool' ? (
                  <select id="cf-value" value={value} onChange={(e) => setValue(e.target.value)} className="mt-1 h-11 px-3 rounded-xl border border-line bg-white"><option value="true">yes</option><option value="false">no</option></select>
                ) : param.type === 'choice' ? (
                  <select id="cf-value" value={value} onChange={(e) => setValue(e.target.value)} className="mt-1 h-11 px-3 rounded-xl border border-line bg-white">{(param.choices || []).map((c) => <option key={c} value={c}>{humanize(c)}</option>)}</select>
                ) : (
                  <input id="cf-value" type="number" inputMode="numeric" min={param.min} max={param.max} step="1" value={value} onChange={(e) => setValue(e.target.value)}
                    aria-invalid={!!error && error.kind === 'input'} aria-describedby={error ? 'cf-err' : undefined}
                    className="w-40 h-11 px-3 rounded-xl border border-line bg-white text-[15px] tabular focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-400" />
                )}
                {outOfRange && value !== '' && <p className="mt-1.5 text-[12.5px] text-orange-700">Must be between {param.min} and {param.max}.</p>}
                {error && <div id="cf-err" className="mt-3"><ApiErrorBanner error={error} onRetry={() => submit({ preventDefault() {} })} context={{ limit: "Today's limit for new simulations is reached. You can still open the demo run and any finished run." }} /></div>}
              </div>
            )}
            <div className="flex items-center gap-3 flex-wrap">
              <Button type="submit" variant="primary" size="lg" disabled={busy || outOfRange} iconRight={<IconArrow size={18} />}>{busy ? 'Starting…' : 'Run the what-if'}</Button>
              <span className="text-[12.5px] text-ink-3">Uses one of today's runs and real AI calls (30–60 s).</span>
            </div>
          </form>
        )}
      </Card>
      <Card>
        <CardTitle title="What-ifs from this run" sub="Made in this browser" />
        {earlier.length === 0 && <p className="text-[13px] text-ink-3">None yet in this browser. You can also compare with any run ID in the Compare tab.</p>}
        <ul className="flex flex-col gap-2">
          {earlier.map((r) => (
            <li key={r} className="flex items-center justify-between gap-2 rounded-xl bg-white/60 border border-white px-3 py-2">
              <IdTag id={r} label="Run" />
              <Button size="sm" onClick={() => navigate(`/run/${run.run_id}/analysis/compare/${r}`)} icon={<IconSplit size={14} />}>Compare</Button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ Compare */
function ComparePicker({ run }) {
  const s = useSession()
  const [other, setOther] = useState('')
  const known = (s.whatIfs?.[run.run_id] || [])
  return (
    <Card>
      <EmptyState icon={<IconSplit size={28} className="text-ink-3" />} title="Pick a run to compare with">
        Compare this run with a what-if made from it. Run a what-if first, or type the ID of one you already have.
      </EmptyState>
      <form className="flex gap-2 max-w-md mx-auto" onSubmit={(e) => { e.preventDefault(); if (other.trim()) navigate(`/run/${run.run_id}/analysis/compare/${other.trim()}`) }}>
        <label htmlFor="cmp-id" className="sr-only">Run ID to compare with</label>
        <div className="relative flex-1"><IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" size={16} />
          <input id="cmp-id" value={other} onChange={(e) => setOther(e.target.value)} placeholder="L-960f5653" className="w-full h-10 pl-9 pr-3 rounded-full border border-line bg-white/85 font-mono text-[13px] focus:outline-none focus:ring-4 focus:ring-blue-100" /></div>
        <Button type="submit" variant="primary">Compare</Button>
      </form>
      {known.length > 0 && <div className="flex flex-wrap gap-2 justify-center mt-4">{known.map((r) => <Button key={r} size="sm" onClick={() => navigate(`/run/${run.run_id}/analysis/compare/${r}`)}>{r}</Button>)}</div>}
      <div className="flex justify-center mt-4"><Button variant="ghost" onClick={() => navigate(`/run/${run.run_id}/analysis/whatif`)}>Run a what-if instead</Button></div>
    </Card>
  )
}

function Compare({ run, words, other }) {
  const cmp = useLoad(other ? `compare:${run.run_id}:${other}` : null, () => api.compare(run.run_id, other), { keep: false })
  const stillRunning = cmp.error instanceof ApiError && cmp.error.kind === 'conflict'
  useEffect(() => {
    if (!stillRunning) return
    const t = setTimeout(cmp.reload, 3000)
    return () => clearTimeout(t)
  }, [stillRunning, cmp]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!other) return <ComparePicker run={run} />
  if (stillRunning) return <Card><EmptyState title="The other run is still going">The comparison opens when it ends. Checking every 3 seconds. <Button variant="ghost" onClick={() => navigate(`/run/${other}`)}>Watch it</Button></EmptyState></Card>
  if (cmp.loading && !cmp.data) return <LoadingBlock label="Comparing…" />
  if (cmp.error) return <ApiErrorBanner error={cmp.error} onRetry={cmp.reload} />
  const c = cmp.data
  if (!c) return null
  const [a, b] = c.runs
  const per = words.period
  const rows = [
    ['Longest queue', a.queue_length.longest, b.queue_length.longest],
    [`${cap(per)}s over capacity`, a.queue_length.periods_over_capacity, b.queue_length.periods_over_capacity],
    [`Average wait (${per}s)`, a.waiting_time.mean, b.waiting_time.mean],
    [`Longest wait (${per}s)`, a.waiting_time.longest, b.waiting_time.longest],
    [`${cap(words.terms.requests)} filed`, a.requests_filed, b.requests_filed],
    ['Never decided', a.waiting_time.never_decided, b.waiting_time.never_decided],
    ['Waiting at the check', a.pending_at_check, b.pending_at_check],
  ]
  const people = Array.from(new Set([...a.checks, ...b.checks].map((x) => x.person)))
  const checkOf = (r, p) => r.checks.filter((x) => x.person === p).slice(-1)[0]
  const val = (x) => (x == null ? '—' : Math.round(x * 100) / 100)
  return (
    <div className="flex flex-col gap-4">
      <WithinModelBanner text={c.label} />
      <Card className="!p-5">
        <h3 className="text-[16px] font-semibold mb-3">What changed</h3>
        <div className="flex flex-wrap gap-2">
          {c.differences.map((d) => {
            const p = words.param(d.parameter)
            return <span key={d.parameter} className="inline-flex items-center gap-2 h-9 px-4 rounded-full bg-white border border-line text-[14px]"><span className="text-ink-2">{cap(p?.description || humanize(d.parameter))}:</span><span className="font-semibold tabular">{formatValue(d.from, p)} → {formatValue(d.to, p)}</span></span>
          })}
          {!c.differences.length && <span className="text-[13px] text-ink-3">No condition differs.</span>}
        </div>
        {!c.matched && <Banner tone="orange" className="mt-3" title="Not a controlled comparison">These runs differ in more than one condition, or in none, so this isn't a controlled comparison.</Banner>}
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardTitle title="Queue and waiting" sub={`Measured over the whole term, in ${per}s`} />
          <table className="w-full text-[13.5px]">
            <thead><tr className="text-left text-[12px] text-ink-3"><th className="font-medium py-2">Measure</th><th className="font-medium py-2 text-right">This run <span className="font-mono">{a.run_id}</span></th><th className="font-medium py-2 text-right">What-if <span className="font-mono">{b.run_id}</span></th></tr></thead>
            <tbody>{rows.map(([k, x, y]) => (
              <tr key={k} className="border-t border-line"><td className="py-2.5 text-ink-2">{k}</td><td className="py-2.5 text-right tabular font-medium">{val(x)}</td><td className={cx('py-2.5 text-right tabular font-medium', x !== y && 'text-blue-700')}>{val(y)}</td></tr>
            ))}</tbody>
          </table>
        </Card>
        <Card>
          <CardTitle title={cap(words.template.checks?.[0]?.label || 'Checks')} sub="Rows where the result flips are marked" />
          <table className="w-full text-[13.5px]">
            <thead><tr className="text-left text-[12px] text-ink-3"><th className="font-medium py-2">Person</th><th className="font-medium py-2 text-right">This run</th><th className="font-medium py-2 text-right">What-if</th></tr></thead>
            <tbody>{people.map((p) => {
              const x = checkOf(a, p)
              const y = checkOf(b, p)
              const flip = x && y && x.passed !== y.passed
              const cell = (z) => z ? <span className={cx('inline-flex items-center gap-1.5 tabular font-medium', z.passed ? 'text-ok' : 'text-bad')}>{z.value != null ? (words.terms.count.includes('%') ? pct(z.value) : z.value) : '—'} {z.passed ? '✓' : '✕'}</span> : <span className="text-ink-3">—</span>
              return (
                <tr key={p} className={cx('border-t border-line', flip && 'bg-orange-50')}>
                  <td className="py-2.5"><div className="flex items-center gap-2"><PersonAvatar colour={words.colour(p)} size={24} /><span>{words.name(p)}</span>{flip && <Badge tone="orange" className="!h-5">flipped</Badge>}</div></td>
                  <td className="py-2.5 text-right">{cell(x)}</td><td className="py-2.5 text-right">{cell(y)}</td>
                </tr>
              )
            })}</tbody>
          </table>
        </Card>
      </div>
      <Banner tone="glass" title="Read this before deciding">{c.note}</Banner>
      <Card className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
        <div>
          <h3 className="text-[16px] font-semibold">You decide</h3>
          <p className="text-[13px] text-ink-3 mt-0.5">No AI verdict, no score.</p>
          <p className="text-[13.5px] text-ink-2 mt-3 max-w-xl">Look at the findings of each run, then try another condition or test a changed policy.</p>
          <div className="flex flex-wrap gap-3 mt-3 text-[13px]">
            <a className="text-blue-700 hover:underline" href={`#/run/${a.run_id}/analysis/findings`}>Findings of {a.run_id} ({a.check_failed.length} failed)</a>
            <a className="text-blue-700 hover:underline" href={`#/run/${b.run_id}/analysis/findings`} onClick={() => rememberRun(b.run_id)}>Findings of {b.run_id} ({b.check_failed.length} failed)</a>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button onClick={() => navigate(`/run/${a.run_id}/analysis/whatif`)}>Try another condition</Button>
          <Button variant="primary" onClick={() => navigate('/setup')}>Test a new policy</Button>
        </div>
      </Card>
    </div>
  )
}

/* -------------------------------------------------------------------- Shell */
export default function Analysis({ id, tab: rawTab, arg }) {
  const tab = TABS.includes(rawTab) ? rawTab : 'summary'
  const { run, events, error, loading } = useRun(id)
  const t = useTemplate(templateIdOf(run?.template))
  const bp = useBlueprint(run?.blueprint_id)
  const words = useMemo(() => (t.data ? makeWords(t.data) : null), [t.data])
  const fs = useFindings(id, run?.status)
  const findings = fs.data?.findings || []
  useEffect(() => { if (run?.run_id) rememberRun(run.run_id, run.blueprint_id) }, [run?.run_id, run?.blueprint_id])

  // Evidence with no finding chosen: open the first one.
  useEffect(() => {
    if (tab === 'evidence' && !arg && findings.length) navigate(`/run/${id}/analysis/evidence/${findings[0].finding_id}`)
  }, [tab, arg, findings.length, id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <LoadingBlock label="Opening the run…" />
  if (error) return <ApiErrorBanner error={error} onRetry={() => window.location.reload()} context={{ notfound: 'No run with that ID.' }} />
  if (!run || !words) return <LoadingBlock />

  const finished = run.status !== 'running'
  const go = (t2) => navigate(`/run/${id}/analysis${t2 === 'summary' ? '' : `/${t2}`}`)
  const toEvidence = (fid) => navigate(`/run/${id}/analysis/evidence/${fid}`)

  return (
    <div>
      <PageHeader step={4} recorded eyebrow="Analysis" title={`What happened in run ${run.run_id}`}
        subtitle={`${words.template.title}. Findings, the evidence behind them, and what changes when one condition does.`}
        meta={<><IdTag id={run.run_id} label="Run" /><StatusBadge status={run.status} /></>}
        actions={<Button icon={<IconBack size={16} />} onClick={() => navigate(`/run/${id}`)}>Back to the map</Button>} />
      {!finished ? (
        <Card><EmptyState title="Findings appear when the run ends" action={<Button variant="primary" onClick={() => navigate(`/run/${id}`)}>Watch it</Button>}>This run is still going ({words.period} {run.period} of {run.periods}).</EmptyState></Card>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="overflow-x-auto -mx-1 px-1 pb-1">
            <Tabs value={tab} onChange={go} tabs={[
              { id: 'summary', label: 'Summary' },
              { id: 'findings', label: 'Findings', count: findings.length },
              { id: 'evidence', label: 'Evidence', disabled: !findings.length, hint: findings.length ? undefined : 'No findings in this run' },
              { id: 'whatif', label: 'What if?' },
              { id: 'compare', label: 'Compare' },
            ]} />
          </div>
          {fs.error && <ApiErrorBanner error={fs.error} onRetry={fs.reload} />}
          {fs.loading && tab !== 'whatif' && tab !== 'compare' ? <LoadingBlock label="Finding what went wrong…" /> : (
            <div className="anim-rise" key={tab + (arg || '')}>
              {tab === 'summary' && <Summary run={run} events={events} words={words} findings={findings} onEvidence={toEvidence} blueprint={bp.data} />}
              {tab === 'findings' && <Findings run={run} events={events} words={words} findings={findings} onEvidence={toEvidence} />}
              {tab === 'evidence' && <Evidence run={run} events={events} words={words} findings={findings} fid={arg} />}
              {tab === 'whatif' && <WhatIf run={run} words={words} bp={bp.data} />}
              {tab === 'compare' && <Compare run={run} words={words} other={arg} />}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
