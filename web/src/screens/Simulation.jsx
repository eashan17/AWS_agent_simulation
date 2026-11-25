// S5 Simulation: watch the term unfold, see who decided what and why, then go to the findings.
import { useEffect, useMemo, useState } from 'react'
import { Banner, Button, Card, CardTitle, IdTag, Progress } from '../ui/primitives.jsx'
import { IconAlert, IconArrow } from '../ui/icons.jsx'
import { PageHeader } from '../ui/shell.jsx'
import { ApiErrorBanner, LoadingBlock } from '../domain/feedback.jsx'
import { StatusBadge } from '../domain/labels.jsx'
import { DEFAULT_FILTERS, EventFeed } from '../domain/events.jsx'
import { PeopleStrip, usePeopleFacts } from '../domain/people.jsx'
import World from '../sim/World.jsx'
import TimeRuler from '../sim/TimeRuler.jsx'
import PlaybackBar from '../sim/PlaybackBar.jsx'
import { buildLayout } from '../sim/layout.js'
import { clockAt, deriveWorld, usePlayback } from '../sim/director.js'
import { api } from '../lib/api.js'
import { templateIdOf, useBlueprint, useRun, useTemplate } from '../lib/hooks.js'
import { navigate } from '../lib/router.js'
import { rememberRun } from '../lib/session.js'
import { cap, checkpointValue, duration, makeWords } from '../lib/words.js'

/** The check's period: where the run recorded it, else the blueprint's checkpoint value (a live run before its check). */
export function checkpointFrom(bp, words, events) {
  const c = events.find((e) => e.type === 'check_evaluated')
  if (c) return c.period
  return checkpointValue(bp?.blueprint?.values, words)
}

/** Stage + term track + playback, reusable by any screen that shows a run. */
export function useStage(events, words, { autoplay = true, speed = 2 } = {}) {
  const sig = useMemo(() => {
    const duty = events.find((e) => e.payload?.duty)?.payload.duty || ''
    const dec = [...new Set(events.filter((e) => ['queue_processed', 'request_decided', 'decision_awaiting'].includes(e.type)).map((e) => e.actor))].join(',')
    return `${duty}|${dec}`
  }, [events])
  const layout = useMemo(() => (words ? buildLayout(words, events) : null), [words, sig]) // eslint-disable-line react-hooks/exhaustive-deps
  const pb = usePlayback(events, { autoplay, initialSpeed: speed })
  const world = useMemo(() => (words ? deriveWorld(events, pb.count, words) : null), [events, pb.count, words])
  const clock = useMemo(() => (words ? clockAt(events, pb.starts, pb.time, pb.count, words) : null), [events, pb.starts, pb.time, pb.count, words])
  return { layout, pb, world, clock }
}

export default function Simulation({ id }) {
  const { run, events, error, loading, pollError } = useRun(id)
  const t = useTemplate(templateIdOf(run?.template))
  const bp = useBlueprint(run?.blueprint_id)
  const words = useMemo(() => (t.data ? makeWords(t.data) : null), [t.data])
  const { layout, pb, world, clock } = useStage(events, words)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [person, setPerson] = useState(null)
  const facts = usePeopleFacts(events, pb.count, words || { outcome: () => '' })
  const [rerun, setRerun] = useState({ busy: false, error: null })

  useEffect(() => { if (run?.run_id) rememberRun(run.run_id, run.blueprint_id) }, [run?.run_id, run?.blueprint_id])
  // space toggles play
  useEffect(() => {
    const on = (e) => {
      if (e.code !== 'Space' || ['INPUT', 'TEXTAREA', 'BUTTON', 'SELECT'].includes(document.activeElement?.tagName)) return
      e.preventDefault(); pb.toggle()
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [pb])

  const disruptions = useMemo(() => {
    const m = {}
    for (const e of events) if (['obstacle', 'capacity_changed', 'occurrence_cancelled'].includes(e.type)) m[e.period] = (m[e.period] || 0) + 1
    return m
  }, [events])

  if (loading) return <LoadingBlock label="Opening the run…" />
  if (error) return <ApiErrorBanner error={error} onRetry={() => window.location.reload()} context={{ notfound: 'No run with that ID.' }} />
  if (!run) return null

  const finished = run.status === 'completed' || run.status === 'degraded'
  const running = run.status === 'running'
  const s = run.summary || {}
  const again = async () => {
    setRerun({ busy: true, error: null })
    try { const r = await api.startRun(run.blueprint_id); rememberRun(r.run_id); navigate(`/run/${r.run_id}`) } catch (err) { setRerun({ busy: false, error: err }) }
  }

  return (
    <div>
      <PageHeader step={3} recorded eyebrow="Simulation" title={words ? words.template.title : 'Simulation'}
        subtitle={running ? `The term is running now. New events appear every few seconds.` : `A simulated term: AI people decide, the rule engine records. Press play to replay it ${words?.period || 'week'} by ${words?.period || 'week'}.`}
        meta={<>
          <IdTag id={run.run_id} label="Run" />
          <StatusBadge status={run.status} />
          <span className="text-[12.5px] text-ink-2 font-medium tabular">{cap(words?.period || 'period')} {run.period || 0} of {run.periods}</span>
          {running && <Progress value={run.period || 0} max={run.periods} className="w-40" label="Progress through the term" />}
          {!running && duration(run.started_at, run.finished_at) && <span className="text-[12px] text-ink-3 font-mono">ran in {duration(run.started_at, run.finished_at)} · {run.model_id}</span>}
        </>}
        actionHint={finished ? "Opens the analysis: findings found by rules from this run's records, and the evidence behind each." : running ? 'The analysis opens when the last week is recorded.' : null}
        actions={finished
          ? <Button variant="primary" size="lg" iconRight={<IconArrow size={18} />} onClick={() => navigate(`/run/${run.run_id}/analysis`)}>See what went wrong</Button>
          : running ? <Button size="lg" disabled>Findings appear when the run ends</Button> : null} />

      <div className="flex flex-col gap-4">
        {pollError && <Banner tone="orange" icon={<IconAlert size={16} />} title="Lost contact with the server">Showing the events so far and trying again every 3 seconds.</Banner>}
        {run.status === 'degraded' && <Banner tone="orange" icon={<IconAlert size={16} />} title="Some AI calls failed or hit the limit">{s.llm_errors || 0} failed call{s.llm_errors === 1 ? '' : 's'}, {s.cap_hits || 0} limit hit{s.cap_hits === 1 ? '' : 's'}; results may be thinner.</Banner>}
        {run.status === 'failed' && (
          <Banner tone="bad" icon={<IconAlert size={16} />} title="This run stopped before the end" action={<Button size="sm" variant="primary" disabled={rerun.busy} onClick={again}>Run it again</Button>}>
            {run.error || 'The run failed.'} The events up to that point are below.
          </Banner>
        )}
        <ApiErrorBanner error={rerun.error} />

        <Card pad={false} className="overflow-hidden">
          <div className="p-3 sm:p-4 pb-0">
            {words && layout && world
              ? <World words={words} layout={layout} world={world} events={events} playback={pb} clock={clock} selected={person} onSelect={setPerson} className="w-full h-auto block rounded-[22px] border border-white" />
              : <div className="aspect-[2/1] skeleton" />}
          </div>
          <div className="px-4 sm:px-6 pt-4">
            {words && <TimeRuler periods={run.periods || words.periods} stepsPerPeriod={words.cal.steps_per_period} position={clock?.position} checkpoint={checkpointFrom(bp.data, words, events)} disruptions={disruptions} label={words.period} stepLabel={words.step} onSeek={(p) => pb.seekPeriod(p)} nowText={clock?.text} />}
          </div>
          <div className="px-4 sm:px-6 pb-5 pt-2">
            {words && <PlaybackBar pb={pb} events={events} words={words} live={running} />}
          </div>
        </Card>

        <div className="grid lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] gap-4 items-start">
          <Card className="flex flex-col">
            <CardTitle title="Timeline" sub={person ? `Only events about ${person}` : 'What happened so far, newest last. Click an event to jump the map there.'}
              action={person && <Button size="sm" variant="quiet" onClick={() => setPerson(null)}>Show everyone ✕</Button>} />
            {words && (
              <EventFeed className="h-[520px]" events={events} count={pb.count} w={words} filters={filters} setFilters={setFilters} person={person}
                onPick={(e) => { pb.pause(); pb.seekIndex(events.indexOf(e)) }} follow={pb.playing} />
            )}
          </Card>
          <Card className="flex flex-col">
            <CardTitle title="People" sub="Click someone to follow them on the map" />
            {words && (
              <div className="thin-scroll overflow-y-auto max-h-[560px] -mx-1 px-1">
                <PeopleStrip words={words} facts={facts} selected={person} onSelect={setPerson} decisionsByAgent={pb.atEnd ? s.decisions_by_agent : null} />
              </div>
            )}
          </Card>
        </div>

        {finished && (
          <Card className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3">
              {[
                ['AI decisions', s.decisions ?? '—'],
                ['Model calls', s.llm_calls ?? '—'],
                ['Refused actions', s.rejected?.length ?? 0],
                ['Errors', s.llm_errors ?? 0],
              ].map(([k, v]) => <div key={k}><div className="text-[12px] text-ink-3">{k}</div><div className="text-[22px] font-medium tabular">{v}</div></div>)}
            </div>
            <div className="flex items-center gap-3">
              <p className="text-[13px] text-ink-2 max-w-xs">The run is finished. Findings come from rules over these records, not from an AI summary.</p>
              <Button variant="primary" iconRight={<IconArrow size={16} />} onClick={() => navigate(`/run/${run.run_id}/analysis`)}>See what went wrong</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
