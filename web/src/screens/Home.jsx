// S1 Overview: what RuleStorm does, and the demo or a new test in one click.
// MatrAIx ideas: centred hero with a ruled mono eyebrow, persona cards floating over the
// product's own map, and the journey drawn as flowing lines through four nodes.
import { useEffect, useMemo, useState } from 'react'
import { Button, Card, CardTitle, cx, LinkButton } from '../ui/primitives.jsx'
import { IconArrow, IconSearch, IconSpark } from '../ui/icons.jsx'
import { JOURNEY } from '../ui/shell.jsx'
import { navigate, href } from '../lib/router.js'
import { useRun, useTemplate, useTemplates, templateIdOf } from '../lib/hooks.js'
import { ApiError, api } from '../lib/api.js'
import { humanize, makeWords } from '../lib/words.js'
import { buildLayout } from '../sim/layout.js'
import { clockAt, deriveWorld, usePlayback } from '../sim/director.js'
import World from '../sim/World.jsx'
import { PersonAvatar } from '../sim/Agent.jsx'
import { setSession } from '../lib/session.js'

function PersonaCard({ id, words, study, className, delay = 0 }) {
  return (
    <div className={cx('glass absolute z-10 flex items-center gap-3 rounded-2xl pl-2.5 pr-4 py-2.5 anim-float', className)} style={{ animationDelay: `${delay}s` }}>
      <PersonAvatar colour={words.colour(id)} size={34} />
      <div className="leading-tight">
        <div className="text-[13.5px] font-semibold">{humanize(id)}</div>
        <div className="text-[11.5px] text-ink-3">{words.roleLabel(id)} · {words.label(id)}</div>
      </div>
      <span className="ml-2 inline-flex items-center gap-1.5 font-mono text-[10.5px] text-ok whitespace-nowrap"><span className="w-1.5 h-1.5 rounded-full bg-ok" />{study}</span>
    </div>
  )
}

/** The demo run, playing quietly on a loop: the product's own map as the hero image. */
function StagePreview() {
  const { run, events } = useRun('demo')
  const t = useTemplate(templateIdOf(run?.template))
  const words = useMemo(() => (t.data ? makeWords(t.data) : null), [t.data])
  const layout = useMemo(() => (words ? buildLayout(words, events) : null), [words, events])
  const pb = usePlayback(events, { autoplay: true, initialSpeed: 3 })
  const world = useMemo(() => (words ? deriveWorld(events, pb.count, words) : null), [events, pb.count, words])
  const clock = words ? clockAt(events, pb.starts, pb.time, pb.count, words) : null
  const restart = pb.restart
  useEffect(() => {
    if (!pb.atEnd || !events.length) return
    const tm = setTimeout(restart, 1800)
    return () => clearTimeout(tm)
  }, [pb.atEnd, events.length]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!words || !world) return <div className="aspect-[2/1] rounded-[var(--radius-panel)] skeleton" />
  const study = `in the ${humanize(t.data.id)} demo`
  const [p1, p2, p3] = words.travellers
  return (
    <div className="relative px-0 lg:px-10">
      <div className="glass rounded-[var(--radius-panel)] p-2.5">
        <World words={words} layout={layout} world={world} events={events} playback={pb} clock={clock} className="w-full h-auto block rounded-[22px]" />
      </div>
      {/* floating over the edges of the map, where nothing that means anything is drawn */}
      {p1 && <PersonaCard id={p1} words={words} study={study} className="hidden md:flex left-0 -bottom-7" />}
      {p2 && <PersonaCard id={p2} words={words} study={study} className="hidden lg:flex left-[34%] -top-8" delay={0.8} />}
      {p3 && <PersonaCard id={p3} words={words} study={study} className="hidden md:flex right-0 -bottom-7" delay={1.6} />}
    </div>
  )
}

export function OpenById() {
  const [id, setId] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const go = async (e) => {
    e.preventDefault()
    const v = id.trim()
    if (!v) { setErr('Type a run ID, for example demo.'); return }
    setBusy(true); setErr(null)
    try {
      await api.run(v)
      setSession({ runId: v })
      navigate(`/run/${v}`)
    } catch (x) {
      setErr(x instanceof ApiError && x.kind === 'notfound' ? 'No run with that ID.' : x instanceof ApiError && x.kind === 'network' ? "The server didn't answer. Try again in a minute." : 'Could not open that run. Try again.')
    } finally { setBusy(false) }
  }
  return (
    <form onSubmit={go} className="flex flex-col gap-1.5">
      <label htmlFor="open-run" className="text-[13px] font-medium">Open a run by ID</label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" size={16} />
          <input id="open-run" value={id} onChange={(e) => setId(e.target.value)} placeholder="demo, or a run ID like L-…"
            aria-invalid={!!err} aria-describedby={err ? 'open-run-err' : undefined}
            className="w-full h-10 pl-9 pr-3 rounded-full border border-line bg-white/85 font-mono text-[13px] focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-400" />
        </div>
        <Button type="submit" disabled={busy}>Open</Button>
      </div>
      {err && <p id="open-run-err" className="text-[12.5px] text-bad">{err}</p>}
    </form>
  )
}

export default function Home() {
  const templates = useTemplates()
  return (
    <div className="flex flex-col gap-20 pb-4">
      {/* hero */}
      <section className="flex flex-col items-center text-center pt-6 anim-rise">
        <div className="eyebrow flex items-center gap-4"><span className="w-14 h-px bg-ink-3/50" />RuleStorm · simulate before rollout<span className="w-14 h-px bg-ink-3/50" /></div>
        <h1 className="mt-6 text-[40px] sm:text-[56px] leading-[1.02] font-semibold tracking-[-0.035em] max-w-4xl">
          See how a rule plays out <span className="text-blue-600">before it reaches real people</span>
        </h1>
        <p className="mt-5 text-[16px] text-ink-2 max-w-2xl">See how a rule plays out against students' real constraints and staff capacity, before rollout.</p>
        <span className="mt-5 inline-flex items-center gap-2 h-9 px-4 rounded-full bg-white/70 border border-white text-[13px] font-medium shadow-[0_8px_24px_-16px_rgba(20,34,80,.4)]">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-500" /> It explores possible responses in a simulation; it does not predict what a real college will do.
        </span>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <Button variant="primary" size="lg" iconRight={<IconArrow size={18} />} onClick={() => { setSession({ runId: 'demo' }); navigate('/run/demo') }}>Open the demo run</Button>
          <LinkButton href={href('/setup')} size="lg" icon={<IconSpark size={18} />}>Test a new policy</LinkButton>
        </div>
        <p className="mt-3 text-[12.5px] text-ink-3">The demo is a real recorded run: it opens at once and makes no AI calls.</p>
      </section>

      <StagePreview />

      {/* the journey as flowing lines through four nodes */}
      <section aria-labelledby="how">
        <div className="flex items-center gap-3"><span className="font-mono text-[12px] text-blue-600">01</span><span className="w-12 h-px bg-blue-600" /><span className="font-mono text-[12px] text-ink-2">How a test works</span></div>
        <h2 id="how" className="mt-4 text-[44px] leading-none font-semibold tracking-[-0.035em]">Four steps</h2>
        <p className="mt-2 text-[17px] text-ink-2">Setup, Review, Simulate and Analyse.</p>
        <div className="relative mt-4 -mx-4 sm:-mx-6 lg:-mx-9">
          <svg viewBox="0 0 1200 220" className="w-full h-auto" aria-hidden>
            {Array.from({ length: 9 }).map((_, k) => (
              <path key={k} d={`M -20 ${120 + k * 4} C 200 ${40 + k * 9}, 330 ${210 - k * 6}, 560 ${118 - k * 3} S 900 ${30 + k * 10}, 1220 ${100 + k * 5}`}
                fill="none" stroke={k % 3 === 0 ? 'var(--color-blue-400)' : 'var(--color-blue-200)'} strokeWidth={k === 4 ? 1.6 : 1} opacity={0.35 + (k % 4) * 0.12} />
            ))}
            {[...Array(36)].map((_, k) => <circle key={`d${k}`} cx={(k * 97) % 1200} cy={60 + ((k * 53) % 120)} r={k % 5 === 0 ? 2.4 : 1.6} fill={k % 7 === 0 ? 'var(--color-ok)' : 'var(--color-blue-400)'} opacity=".55" />)}
            {[[150, 108], [430, 150], [700, 86], [1000, 70]].map(([x, y], i) => (
              <g key={i} transform={`translate(${x} ${y})`}>
                <circle r="11" fill="#fff" stroke={['var(--color-blue-600)', 'var(--p4)', 'var(--color-ok)', 'var(--color-orange-500)'][i]} strokeWidth="2" />
                <circle r="4" fill="none" stroke={['var(--color-blue-600)', 'var(--p4)', 'var(--color-ok)', 'var(--color-orange-500)'][i]} strokeWidth="2" />
                <text x="18" y="-12" fontSize="19" fontWeight="600" fill="var(--color-ink-2)">{JOURNEY[i].label}</text>
              </g>
            ))}
          </svg>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-5 mt-2">
          {JOURNEY.map((s) => (
            <div key={s.id}>
              <div className="font-mono text-[11px] text-ink-3">0{s.n}</div>
              <div className="text-[15px] font-semibold mt-1">{s.sub}</div>
              <p className="text-[13.5px] text-ink-2 mt-1">{{
                setup: 'Write the rule, its purpose and the setting in plain words.',
                review: "RuleStorm builds a simulation. You check which values are your facts and which are the AI's assumptions, then approve.",
                simulate: 'AI people live through a term on a deterministic rule engine. Watch who decides what, and why.',
                analyse: 'Findings come from rules over the records. Trace each to its evidence, change one condition, compare.',
              }[s.id]}</p>
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="model" className="flex flex-col gap-5">
        <div className="flex items-center gap-3"><span className="font-mono text-[12px] text-blue-600">02</span><span className="w-12 h-px bg-blue-600" /><span className="font-mono text-[12px] text-ink-2">What it can model</span></div>
        <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
          <Card>
            <CardTitle title="Policy templates" sub="Each policy you write is matched to one of these, or RuleStorm says it can't model it yet" />
            <ul className="flex flex-col">
              {templates.loading && [0, 1].map((i) => <li key={i} className="h-16 skeleton mb-2" />)}
              {templates.error && <li className="text-[13px] text-ink-3">The list of templates didn't load. You can still open the demo run or test a new policy.</li>}
              {(templates.data || []).map((t, i) => (
                <li key={t.id} className="flex gap-4 py-4 border-t border-line/70 first:border-0 first:pt-0">
                  <span className={cx('mt-1 w-2.5 h-2.5 rounded-full shrink-0', i === 0 ? 'bg-blue-600' : 'bg-orange-500')} />
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap"><h3 className="text-[15px] font-semibold">{t.title}</h3><span className="font-mono text-[11px] text-ink-3">{t.id}@{t.version}</span></div>
                    <p className="text-[13.5px] text-ink-2 mt-1">{t.scope}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="flex flex-col">
            <CardTitle title="Open a run" sub="Every run keeps its ID; anyone with it sees the same run and evidence" />
            <OpenById />
          </Card>
        </div>
      </section>
    </div>
  )
}
