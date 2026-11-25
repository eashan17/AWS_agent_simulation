// The stage: one SVG world composed from scenery, zones and agents, driven by the director.
// Positions animate in a requestAnimationFrame loop (no React render per frame); everything
// that means something (zones, marks, bubbles) comes from the derived world state.
import { useEffect, useMemo, useRef } from 'react'
import { STAGE, planPath, spotFor } from './layout.js'
import { BUBBLE_SECONDS } from './director.js'
import { Pebble } from './Agent.jsx'
import { Commons, DutyBuilding, Desk, Gate, Hazard, House, StageDefs, Terrain } from './scenery.jsx'
import Clock from './Clock.jsx'

const tickOf = (e) => (e ? `${e.period}:${e.step ?? 'end'}` : null)

function BubbleBox({ kind, text, align, below }) {
  const tone = kind === 'refused'
    ? 'border-bad/40 bg-white text-ink'
    : kind === 'think' ? 'border-blue-200 bg-white/95 text-ink' : 'border-orange-200 bg-white text-ink'
  const label = kind === 'refused' ? 'Refused' : kind === 'think' ? 'Thinking' : 'Says'
  const short = text && text.length > 150 ? `${text.slice(0, 148)}…` : text
  return (
    <div style={{ display: 'flex', height: '100%', alignItems: below ? 'flex-start' : 'flex-end', justifyContent: align === 'right' ? 'flex-end' : align === 'left' ? 'flex-start' : 'center' }}>
      <div className={`anim-rise rounded-2xl border shadow-[var(--shadow-lift)] px-3 py-2 text-[11.5px] leading-snug max-w-[230px] ${tone}`}>
        <div className={`font-mono text-[9.5px] uppercase tracking-wider mb-0.5 ${kind === 'refused' ? 'text-bad' : kind === 'think' ? 'text-blue-700' : 'text-orange-700'}`}>
          {kind === 'refused' ? '✕ ' : ''}{label}
        </div>
        {kind === 'think' ? <span>“{short}”</span> : short}
      </div>
    </div>
  )
}

export default function World({ words, layout, world, events, playback, clock, selected, onSelect, className, showLabels = true }) {
  const ids = useMemo(() => [...words.travellers, ...words.staff.filter((id) => !!layout.staffSpot[id])], [words, layout])
  const groupRefs = useRef({})
  const trailRefs = useRef({})
  const bubbleRefs = useRef({})
  const linkRefs = useRef([])
  const anim = useRef({})
  const lastSeek = useRef(-1)
  const speedRef = useRef(playback.speed)
  speedRef.current = playback.speed
  const linksRef = useRef(world.links)
  linksRef.current = world.links

  // targets from the logical world
  useEffect(() => {
    const snap = lastSeek.current !== playback.seekNonce
    lastSeek.current = playback.seekNonce
    for (const id of ids) {
      const isTraveller = words.travellers.includes(id)
      const zone = isTraveller ? world.agents[id]?.zone || 'home' : 'post'
      const spec = isTraveller ? spotFor(layout, id, zone) : { xy: layout.staffSpot[id], t: null }
      const a = anim.current[id]
      if (!a) { anim.current[id] = { x: spec.xy[0], y: spec.xy[1], zone, spec, path: [], trail: [], dir: 0 }; continue }
      if (a.zone === zone && !snap) continue
      if (snap) { a.x = spec.xy[0]; a.y = spec.xy[1]; a.path = []; a.trail = [] }
      else a.path = planPath(layout, id, a.spec, spec)
      a.zone = zone
      a.spec = spec
    }
  }, [world, ids, layout, words, playback.seekNonce])

  // the motion loop
  useEffect(() => {
    let raf
    let last = performance.now()
    const loop = (now) => {
      const dt = Math.min(0.06, (now - last) / 1000)
      last = now
      const v = 260 * Math.max(1, Math.min(6, speedRef.current))
      for (const id of ids) {
        const a = anim.current[id]
        const g = groupRefs.current[id]
        if (!a || !g) continue
        let budget = v * dt
        let moved = false
        while (budget > 0 && a.path.length) {
          const [tx, ty] = a.path[0]
          const dx = tx - a.x
          const dy = ty - a.y
          const d = Math.hypot(dx, dy)
          if (d <= budget) { a.x = tx; a.y = ty; a.path.shift(); budget -= d } else { a.x += (dx / d) * budget; a.y += (dy / d) * budget; budget = 0 }
          if (Math.abs(dx) > 0.5) a.dir = dx > 0 ? 1 : -1
          moved = true
        }
        g.setAttribute('transform', `translate(${a.x.toFixed(1)} ${a.y.toFixed(1)})`)
        g.classList.toggle('is-walking', moved)
        const pupils = g.querySelector('[data-pupils]')
        if (pupils) pupils.setAttribute('transform', `translate(${moved ? a.dir * 1.3 : 0} 0)`)
        // trail
        const lastPt = a.trail[a.trail.length - 1]
        if (moved && (!lastPt || Math.hypot(lastPt[0] - a.x, lastPt[1] - a.y) > 6)) a.trail.push([a.x, a.y + 16])
        if (!moved && a.trail.length && Math.random() < 0.25) a.trail.shift()
        if (a.trail.length > 40) a.trail.shift()
        const tr = trailRefs.current[id]
        if (tr) tr.setAttribute('points', a.trail.map((p) => p.join(',')).join(' '))
        const b = bubbleRefs.current[id]
        if (b) b.setAttribute('transform', `translate(${a.x.toFixed(1)} ${a.y.toFixed(1)})`)
      }
      linksRef.current.forEach((l, i) => {
        const el = linkRefs.current[i]
        const A = anim.current[l.from]
        const B = anim.current[l.to]
        if (el && A && B) el.setAttribute('d', `M ${A.x} ${A.y - 6} Q ${(A.x + B.x) / 2} ${Math.min(A.y, B.y) - 70} ${B.x} ${B.y - 6}`)
      })
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [ids])

  const tick = world.tick
  const visibleBubble = (b) => {
    if (!b) return false
    if (tickOf(events[b.i]) !== tick) return false
    const t0 = playback.starts[b.i] ?? 0
    return playback.time - t0 < BUBBLE_SECONDS
  }
  const checkResults = Object.values(world.checks).filter((c) => events[c.i]?.period === world.period)
  const deskRule = layout.zones.desk.staff.find((id) => !words.isAI(id))
  const dutyRule = layout.zones.duty.staff.find((id) => !words.isAI(id))
  const checkRule = layout.zones.check.staff.find((id) => !words.isAI(id))
  const night = words.step === 'night'

  return (
    <svg viewBox={`0 0 ${STAGE.w} ${STAGE.h}`} className={className} role="img" aria-label={`Simulation stage, ${words.where(world.period, world.step)}`}>
      <StageDefs />
      <style>{`.is-walking .pebble-body{animation:rs-float .38s ease-in-out infinite}.pebble-body{animation:rs-float 3.4s ease-in-out infinite}`}</style>
      <Terrain night={night} />
      <Commons zone={layout.zones.commons} />

      {layout.houses.map((h) => (
        <House key={h.id} x={h.x} y={h.y} colour={words.colour(h.id)} label={words.name(h.id)} mark={world.agents[h.id]?.zone === 'home' ? world.agents[h.id]?.mark : null} />
      ))}

      <DutyBuilding zone={layout.zones.duty} cancelled={world.duty.cancelled} missedCount={world.phase === 'step' ? world.duty.missedCount : 0} active={world.phase === 'step'} ruleLabel={dutyRule ? words.roleLabel(dutyRule) : null} />
      <Desk zone={layout.zones.desk} desk={{ ...world.desk, capacityNote: world.desk.capacityNote?.period === world.period ? world.desk.capacityNote : null }} ruleLabel={deskRule ? words.roleLabel(deskRule) : null} />
      <Gate zone={layout.zones.check} results={checkResults} ruleLabel={checkRule ? words.roleLabel(checkRule) : null} />

      {world.hazards.slice(-1).map((h) => (
        <Hazard key={h.i} x={layout.hazard[0]} y={layout.hazard[1] - 30} hazard={h} words={words} />
      ))}

      {/* who is talking to whom */}
      <g>
        {world.links.map((l, i) => (
          <path key={`${l.i}-${i}`} ref={(el) => { linkRefs.current[i] = el }} fill="none" stroke="var(--color-orange-400)" strokeWidth="2" strokeDasharray="4 6" opacity={visibleBubble(world.agents[l.from]?.bubble) ? 0.9 : 0} />
        ))}
      </g>

      {/* trails */}
      <g>
        {words.travellers.map((id) => (
          <polyline key={id} ref={(el) => { trailRefs.current[id] = el }} fill="none" stroke={words.colour(id)} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" opacity=".22" />
        ))}
      </g>

      {/* agents */}
      {ids.map((id) => {
        const a = world.agents[id] || {}
        const ai = words.isAI(id)
        if (!ai) return null
        const isSel = selected === id
        const dim = selected && !isSel
        const countTag = a.count && tickOf(events[a.count.i]) === tick ? a.count : null
        return (
          <g key={id} ref={(el) => { groupRefs.current[id] = el }} style={{ cursor: onSelect ? 'pointer' : undefined, opacity: dim ? 0.4 : 1, transition: 'opacity .2s' }}
            onClick={onSelect ? () => onSelect(isSel ? null : id) : undefined}
            role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined} aria-label={onSelect ? `${words.who(id)}${isSel ? ', selected' : ''}` : undefined}
            onKeyDown={onSelect ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(isSel ? null : id) } } : undefined}>
            <title>{words.who(id)}</title>
            {isSel && <circle r="30" fill={words.colour(id)} opacity=".14" />}
            <Pebble colour={words.colour(id)} mood={a.mood} scale={words.travellers.includes(id) ? 1.4 : 1.3} />
            {a.slip && (
              <g transform="translate(21 4) rotate(10) scale(1.35)"><rect x="-6" y="-8" width="12" height="15" rx="2.5" fill="#fff" stroke="var(--color-blue-400)" /><path d="M-3 -3 h6 M-3 1 h6" stroke="var(--color-blue-400)" strokeWidth="1.2" /></g>
            )}
            {a.mark && (
              <g transform="translate(18 -18)" className="svg-pop">
                <circle r="9.5" fill={a.mark === 'met' ? 'var(--color-ok)' : 'var(--color-bad)'} stroke="#fff" strokeWidth="2" />
                <text y="4.5" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{a.mark === 'met' ? '✓' : '✕'}</text>
              </g>
            )}
            {a.badge && !a.mark && (
              <g transform="translate(-19 -19)">
                <circle r="10" fill={a.badge === 'pass' ? 'var(--color-ok)' : a.badge === 'warn' ? 'var(--color-orange-500)' : 'var(--color-bad)'} stroke="#fff" strokeWidth="2" />
                <text y="4.5" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{a.badge === 'pass' ? '✓' : a.badge === 'warn' ? '!' : '✕'}</text>
              </g>
            )}
            {countTag && (
              <g transform="translate(0 -50)" className="svg-pop">
                <rect x="-32" y="-13" width="64" height="25" rx="12.5" fill="var(--color-orange-500)" />
                <text y="4.5" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff">{Number(countTag.value).toFixed(1).replace(/\.0$/, '')}{words.terms.count?.includes('%') ? '%' : ''}</text>
              </g>
            )}
            {isSel && (() => {
              const w = words.name(id).length * 8 + 30
              return (
                <g transform="translate(0 -44)">
                  <rect x={-w / 2} y="-30" width={w} height="26" rx="9" fill={words.colour(id)} stroke="#fff" strokeWidth="2.5" />
                  <path d="M -7 -5 L 0 5 L 7 -5 Z" fill={words.colour(id)} stroke="#fff" strokeWidth="2.5" strokeLinejoin="round" />
                  <rect x="-8" y="-7" width="16" height="4" fill={words.colour(id)} />
                  <text y="-12" textAnchor="middle" fontSize="13" fontWeight="700" fill="#fff">{words.name(id)}</text>
                </g>
              )
            })()}
            {showLabels && !isSel && <text y="40" textAnchor="middle" fontSize="12.5" fontWeight="500" className="font-mono" fill="var(--color-ink-2)" style={{ paintOrder: 'stroke', stroke: 'var(--terrain)', strokeWidth: 4 }}>{words.name(id)}</text>}
          </g>
        )
      })}

      {/* speech and thought, above everything */}
      {ids.map((id) => {
        const b = world.agents[id]?.bubble
        if (!visibleBubble(b)) return <g key={id} ref={(el) => { bubbleRefs.current[id] = el }} />
        const x = anim.current[id]?.x ?? 0
        const y = anim.current[id]?.y ?? 300
        const align = x > 990 ? 'right' : x < 210 ? 'left' : 'center'
        const fx = align === 'right' ? -226 : align === 'left' ? -20 : -120
        const below = y < 175 // near the top edge: open the bubble downwards
        return (
          <g key={id} ref={(el) => { bubbleRefs.current[id] = el }} style={{ pointerEvents: 'none' }}>
            <g transform={below ? 'translate(0 52) scale(1.42)' : 'translate(0 -34) scale(1.42)'}>
              <foreignObject x={fx} y={below ? 0 : -150} width="240" height="150">
                <BubbleBox kind={b.kind} text={b.text} align={align} below={below} />
              </foreignObject>
            </g>
          </g>
        )
      })}

      <Clock clock={clock} words={words} />
    </svg>
  )
}
