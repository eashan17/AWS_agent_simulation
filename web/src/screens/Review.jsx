// S3 Blueprint review and approval, with S4 Stress test as its second tab.
import { useMemo, useState } from 'react'
import { Badge, Banner, Button, Card, CardTitle, EmptyState, IdTag, Tabs } from '../ui/primitives.jsx'
import { IconArrow, IconBolt, IconCheck, IconLock } from '../ui/icons.jsx'
import { PageHeader } from '../ui/shell.jsx'
import { ApiErrorBanner, LoadingBlock, WaitingState } from '../domain/feedback.jsx'
import { FactBadge, FactLegend } from '../domain/labels.jsx'
import { DisruptionList, LabelLines, ParamRow, labelFor, sectionLabels } from '../domain/blueprint.jsx'
import { PersonCard } from '../domain/people.jsx'
import { Machine } from '../sim/Agent.jsx'
import TimeRuler from '../sim/TimeRuler.jsx'
import { api } from '../lib/api.js'
import { useBlueprint, useElapsed, useTemplate, useTemplates } from '../lib/hooks.js'
import { navigate } from '../lib/router.js'
import { rememberRun, setSession } from '../lib/session.js'
import { makeWords, humanize, cap, checkpointValue, formatValue } from '../lib/words.js'

const SECTIONS = [
  { kind: 'policy', title: 'Policy rules', sub: 'What the rule says.' },
  { kind: 'environment', title: 'Conditions', sub: 'The setting the rule meets: capacity, timing and what goes wrong.' },
  { kind: 'people', title: 'People', sub: 'Who lives with the rule, and their slack.' },
]
const variantsCache = new Map()

const checkpointOf = (values, words) => checkpointValue(values, words)

function useStartRun() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const start = async (blueprintId) => {
    setBusy(true); setError(null)
    try {
      const r = await api.startRun(blueprintId)
      rememberRun(r.run_id)
      navigate(`/run/${r.run_id}`)
    } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return { busy, error, start }
}

function Values({ bp, words }) {
  const values = bp.blueprint?.values || {}
  const params = words.template.parameters || []
  const attr = words.template.attributes?.[0]
  const attrParam = params.find((p) => p.type === 'attribute')
  const disruptionsParam = params.find((p) => p.type === 'disruptions')
  const disruptions = disruptionsParam ? values[disruptionsParam.name] || [] : []
  const perPeriod = {}
  for (const d of disruptions) perPeriod[d.period] = (perPeriod[d.period] || 0) + 1
  const ruleRoles = words.roles.filter((r) => !r.llm)

  const order = (list, kind) => list
    .map((p) => ({ p, label: labelFor(bp, p.name, kind) }))
    .sort((a, b) => (a.label?.kind === 'fact' ? 0 : a.label ? 1 : 2) - (b.label?.kind === 'fact' ? 0 : b.label ? 1 : 2))

  return (
    <div className="flex flex-col gap-4">
      {SECTIONS.map((sec) => {
        const list = params.filter((p) => p.kind === sec.kind && p.type !== 'disruptions' && p.type !== 'profiles' && p.type !== 'attribute')
        const secLabels = sectionLabels(bp, sec.kind)
        const sectionLabel = secLabels[0]
        return (
          <Card key={sec.kind}>
            <CardTitle title={sec.title} sub={sec.sub} action={sectionLabel && <FactBadge kind={sectionLabel.kind} statement={sectionLabel.statement} />}>
              <LabelLines labels={secLabels} className="mt-2" />
            </CardTitle>
            {list.length > 0 && <div>{order(list, sec.kind).map(({ p, label }) => <ParamRow key={p.name} param={p} value={values[p.name]} label={label} />)}</div>}

            {sec.kind === 'environment' && disruptionsParam && (
              <div className="mt-5">
                <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                  <h4 className="text-[13.5px] font-semibold">{cap(disruptionsParam.description || 'Disruptions')}</h4>
                  {(() => { const l = labelFor(bp, disruptionsParam.name, 'environment'); return l ? <FactBadge kind={l.kind} statement={l.statement} /> : null })()}
                </div>
                <div className="rounded-2xl bg-white/60 border border-white px-3 pt-2 pb-1 mb-3">
                  <TimeRuler className="px-1 py-2" periods={words.periods} stepsPerPeriod={words.cal.steps_per_period} checkpoint={checkpointOf(values, words)} disruptions={perPeriod} label={words.period} stepLabel={words.step} />
                </div>
                <DisruptionList list={disruptions} words={words} />
              </div>
            )}

            {sec.kind === 'people' && (
              <div className="flex flex-col gap-4">
                {attrParam && (() => {
                  const l = labelFor(bp, attrParam.name, null)
                  return (
                    <div className="flex items-start justify-between gap-4 rounded-2xl bg-white/60 border border-white px-4 py-3">
                      <div className="min-w-0">
                        <div className="text-[13.5px] text-ink">{cap(attrParam.description || humanize(attrParam.name))}</div>
                        <div className="font-mono text-[11px] text-ink-3 mt-0.5">{attrParam.name}</div>
                        <LabelLines labels={l ? [l] : []} className="mt-1.5" />
                      </div>
                      {l && <span className="shrink-0"><FactBadge kind={l.kind} statement={l.statement} /></span>}
                    </div>
                  )
                })()}
                <div className="grid md:grid-cols-2 gap-3">
                  {Object.entries(values.profiles || {}).map(([id, prof]) => (
                    <PersonCard key={id} id={id} words={words} profile={prof} slack={values.slack_min?.[id]} slackLabel={attr?.label || 'slack'} />
                  ))}
                </div>
                {ruleRoles.length > 0 && (
                  <div className="rounded-2xl bg-mist border border-line p-4">
                    <div className="eyebrow !text-[10px] mb-2">Run by rules, not AI</div>
                    <div className="flex flex-wrap gap-3">
                      {ruleRoles.map((r) => (
                        <span key={r.id} className="inline-flex items-center gap-2 h-9 pl-1 pr-3 rounded-full bg-white border border-line text-[13px]">
                          <svg width="28" height="28" viewBox="-16 -16 32 34" aria-hidden><Machine scale={0.85} /></svg>
                          <span className="font-medium">{r.label}</span><span className="text-ink-3 font-mono text-[11px]">{r.rules.map(humanize).join(', ')}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}

function diffEnv(parent, child, words) {
  const out = []
  for (const p of words.template.parameters || []) {
    if (p.kind !== 'environment') continue
    const a = parent?.[p.name]
    const b = child?.[p.name]
    if (JSON.stringify(a) === JSON.stringify(b)) continue
    if (p.type === 'disruptions') {
      const as = new Set((a || []).map((x) => JSON.stringify(x)))
      const bs = new Set((b || []).map((x) => JSON.stringify(x)))
      out.push({ p, added: (b || []).filter((x) => !as.has(JSON.stringify(x))), removed: (a || []).filter((x) => !bs.has(JSON.stringify(x))) })
    } else out.push({ p, from: a, to: b })
  }
  return out
}

function StressTest({ bp, words }) {
  const [state, setState] = useState(() => variantsCache.get(bp.id) || null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [approved, setApproved] = useState({})
  const [cardErr, setCardErr] = useState({})
  const run = useStartRun()
  const seconds = useElapsed(busy)

  if (!bp.approved) {
    return <Card><EmptyState icon={<IconLock size={28} className="text-ink-3" />} title="Approve the blueprint first">The stress test proposes harsher conditions for an approved blueprint. The policy and the people stay the same.</EmptyState></Card>
  }
  const propose = async () => {
    setBusy(true); setError(null)
    try { const r = await api.variants(bp.id); variantsCache.set(bp.id, r); setState(r) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  const approve = async (v) => {
    setCardErr((c) => ({ ...c, [v.id]: null }))
    try { await api.approve(v.id); setApproved((a) => ({ ...a, [v.id]: true })) } catch (err) { setCardErr((c) => ({ ...c, [v.id]: err })) }
  }

  if (busy) return <WaitingState seconds={seconds} title="Looking for weak points" sentence="The AI is proposing up to 3 harsher but plausible versions of the conditions. This takes about 20 seconds." />

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
        <div>
          <h3 className="text-[15px] font-semibold">Stress-test the conditions</h3>
          <p className="text-[13px] text-ink-2 mt-1 max-w-xl">The AI proposes up to 3 harsher versions of the conditions, each aimed at a different weak point. The policy and the people stay the same. Every changed value is an assumption.</p>
        </div>
        <Button variant={state ? 'secondary' : 'primary'} icon={<IconBolt size={16} />} onClick={propose}>{state ? 'Propose again' : 'Propose harsher conditions'}</Button>
      </Card>
      <ApiErrorBanner error={error} onRetry={propose} context={{ limit: "Today's limit for building new simulations is reached." }} />
      <ApiErrorBanner error={run.error} />
      {state?.status && state.status !== 'valid' && state.errors?.length > 0 && <Banner tone="orange" title="Some proposals didn't pass the checks">{state.errors.join('; ')}</Banner>}
      <div className="grid lg:grid-cols-3 gap-4">
        {(state?.variants || []).map((v) => {
          const changes = diffEnv(bp.blueprint.values, v.blueprint?.values, words)
          const isApproved = v.approved || approved[v.id]
          return (
            <Card key={v.id} className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2"><Badge tone="orange">Weak point</Badge><IdTag id={v.id} label="Blueprint" /></div>
              <h4 className="text-[15px] font-semibold">{v.variant}</h4>
              <p className="text-[13px] text-ink-2">{v.weak_point}</p>
              <div className="rounded-xl bg-mist border border-line p-3 flex flex-col gap-2">
                <div className="eyebrow !text-[10px]">What changed</div>
                {changes.length === 0 && <span className="text-[12.5px] text-ink-3">No condition differs.</span>}
                {changes.map((c) => (
                  <div key={c.p.name} className="text-[12.5px]">
                    <div className="flex items-center justify-between gap-2"><span className="text-ink-2">{cap(c.p.description || humanize(c.p.name))}</span><FactBadge kind="assumption" /></div>
                    {c.added || c.removed ? (
                      <ul className="mt-1 text-ink-2">
                        {c.added.map((d, i) => <li key={`a${i}`}>+ {cap(words.period)} {d.period}: {d.description}</li>)}
                        {c.removed.map((d, i) => <li key={`r${i}`} className="text-ink-3 line-through">{cap(words.period)} {d.period}: {d.description}</li>)}
                      </ul>
                    ) : <div className="font-semibold tabular mt-0.5">{formatValue(c.from, c.p)} → {formatValue(c.to, c.p)}</div>}
                  </div>
                ))}
              </div>
              {v.status !== 'valid' && <Banner tone="orange">This variant didn't pass the checks{v.errors?.length ? `: ${v.errors.join('; ')}` : '.'}</Banner>}
              <ApiErrorBanner error={cardErr[v.id]} />
              <div className="mt-auto flex gap-2">
                {!isApproved
                  ? <Button variant="primary" disabled={v.status !== 'valid'} onClick={() => approve(v)} icon={<IconCheck size={16} />}>Approve</Button>
                  : <><Badge tone="ok"><IconLock size={13} /> Approved</Badge><Button variant="primary" disabled={run.busy} onClick={() => run.start(v.id)} iconRight={<IconArrow size={16} />}>Run</Button></>}
              </div>
            </Card>
          )
        })}
      </div>
      {state?.variants?.length > 0 && <p className="text-[12.5px] text-ink-3">Only one simulation runs at a time. Run one variant, then come back for the next.</p>}
    </div>
  )
}

export default function Review({ id, tab }) {
  const bp = useBlueprint(id)
  const t = useTemplate(bp.data?.template_id)
  const templates = useTemplates()
  const words = useMemo(() => (t.data ? makeWords(t.data) : null), [t.data])
  const [approving, setApproving] = useState(false)
  const [approveErr, setApproveErr] = useState(null)
  const [retrying, setRetrying] = useState(false)
  const [retryErr, setRetryErr] = useState(null)
  const run = useStartRun()
  const retrySeconds = useElapsed(retrying)
  const record = bp.data

  if (bp.loading) return <LoadingBlock label="Opening the blueprint…" />
  if (bp.error) return <ApiErrorBanner error={bp.error} onRetry={bp.reload} context={{ notfound: 'No blueprint with that ID.' }} />
  if (!record) return null

  const approve = async () => {
    setApproving(true); setApproveErr(null)
    try { await api.approve(record.id); bp.reload() } catch (err) { setApproveErr(err) } finally { setApproving(false) }
  }
  const retry = async () => {
    setRetrying(true); setRetryErr(null)
    try {
      const n = await api.buildBlueprint(record.policy_id)
      setSession({ blueprintId: n.id })
      navigate(`/blueprint/${n.id}`)
    } catch (err) { setRetryErr(err) } finally { setRetrying(false) }
  }

  const valid = record.status === 'valid'
  const title = valid && words ? words.template.title : record.status === 'out_of_scope' ? "RuleStorm can't model this policy yet" : "The AI's draft didn't pass the checks"

  const actions = !valid ? (
    <Button onClick={() => navigate('/setup')}>Edit the policy</Button>
  ) : !record.approved ? (
    <Button variant="primary" size="lg" onClick={approve} disabled={approving} icon={<IconCheck size={18} />}>{approving ? 'Approving…' : 'Approve'}</Button>
  ) : (
    <>
      <Button onClick={() => navigate(`/blueprint/${record.id}/stress`)} icon={<IconBolt size={16} />}>Stress-test it first</Button>
      <Button variant="primary" size="lg" disabled={run.busy} onClick={() => run.start(record.id)} iconRight={<IconArrow size={18} />}>{run.busy ? 'Starting…' : 'Run this term'}</Button>
    </>
  )

  return (
    <div>
      <PageHeader step={2} eyebrow="Blueprint review" title={title}
        subtitle={valid ? (record.approved ? 'Frozen: every run uses exactly these values.' : 'Check how RuleStorm understood your rule. Your facts are blue; the AI\'s assumptions are orange and dashed. Approve when it reads right.') : null}
        meta={<><IdTag id={record.id} label="Blueprint" />{valid && (record.approved ? <Badge tone="ok"><IconLock size={13} /> Approved and frozen</Badge> : <Badge tone="blue">Waiting for your approval</Badge>)}{record.seconds != null && <span className="text-[12px] text-ink-3 font-mono">built in {Math.round(record.seconds)} s</span>}</>}
        actions={actions}
        actionHint={!valid ? 'Takes you back to the policy text, with your fields kept.' : !record.approved ? 'Freezes these values. Nothing runs until you start it.' : 'Starts a 30–60 second term with exactly these values. One simulation runs at a time.'} />
      <div className="flex flex-col gap-4">
        <ApiErrorBanner error={approveErr} />
        <ApiErrorBanner error={run.error} />

        {record.status === 'out_of_scope' && (
          <Card>
            <p className="text-[14px] text-ink-2"><span className="font-medium text-ink">Why: </span>{record.pick_reason}</p>
            <div className="eyebrow mt-6 mb-3">What it can model</div>
            <div className="grid sm:grid-cols-2 gap-3">
              {(templates.data || []).map((tp) => <div key={tp.id} className="rounded-2xl bg-white/70 border border-white p-4"><div className="font-semibold text-[14px]">{tp.title}</div><div className="text-[12.5px] text-ink-3 mt-1">{tp.scope}</div></div>)}
            </div>
          </Card>
        )}

        {record.status === 'invalid' && (
          retrying ? <WaitingState seconds={retrySeconds} title="Building again" sentence="Reading your policy and building the simulation. This takes up to a minute." /> : (
            <Card className="flex flex-col gap-4">
              <p className="text-[14px] text-ink-2">The values the AI proposed broke one of the template's checks, so this draft can't run. A new try often passes.</p>
              <details className="rounded-xl bg-mist border border-line p-3 text-[13px]"><summary className="cursor-pointer font-medium">What failed ({record.errors?.length || 0})</summary><ul className="mt-2 list-disc pl-5 text-ink-2 font-mono text-[12px]">{(record.errors || []).map((e, i) => <li key={i}>{e}</li>)}</ul></details>
              <ApiErrorBanner error={retryErr} />
              <div><Button variant="primary" onClick={retry}>Try again</Button></div>
            </Card>
          )
        )}

        {valid && words && (
          <>
            <Card className="!p-4 flex flex-col lg:flex-row lg:items-center gap-4 justify-between">
              <div className="flex items-start gap-3 min-w-0">
                <span className="shrink-0"><FactBadge kind="assumption" /></span>
                <p className="text-[13.5px]"><span className="font-medium">Why this model: </span><span className="text-ink-2">{record.pick_reason}</span></p>
              </div>
              <FactLegend />
            </Card>
            <Tabs value={tab} onChange={(v) => navigate(v === 'stress' ? `/blueprint/${record.id}/stress` : `/blueprint/${record.id}`)}
              tabs={[{ id: 'blueprint', label: 'Blueprint' }, { id: 'stress', label: 'Stress test', hint: record.approved ? undefined : 'Approve first' }]} />
            {tab === 'stress' ? <StressTest bp={record} words={words} /> : <Values bp={record} words={words} />}
          </>
        )}
        {valid && !words && <LoadingBlock />}
      </div>
    </div>
  )
}
