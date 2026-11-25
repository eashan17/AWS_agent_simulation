// Stage scenery: a soft toy map on the dotted field. Buildings are glass cards, the road is the
// canvas colour, and orange is kept for things that go wrong. All shapes take positions as props.
import { STAGE } from './layout.js'
import { Machine } from './Agent.jsx'

export function StageDefs() {
  return (
    <defs>
      <filter id="rs-shadow" x="-30%" y="-30%" width="160%" height="170%">
        <feDropShadow dx="0" dy="8" stdDeviation="9" floodColor="#102048" floodOpacity=".14" />
      </filter>
      <filter id="rs-soft" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="18" />
      </filter>
      <pattern id="rs-dots" width="18" height="18" patternUnits="userSpaceOnUse">
        <circle cx="9" cy="9" r="1.1" fill="var(--terrain-dot)" />
      </pattern>
      <linearGradient id="rs-roof" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="var(--color-blue-400)" />
        <stop offset="1" stopColor="var(--color-blue-600)" />
      </linearGradient>
      <linearGradient id="rs-orange" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#FFC08F" />
        <stop offset="1" stopColor="var(--color-orange-500)" />
      </linearGradient>
      <radialGradient id="rs-glow-blue"><stop offset="0" stopColor="var(--color-blue-200)" stopOpacity=".9" /><stop offset="1" stopColor="var(--color-blue-200)" stopOpacity="0" /></radialGradient>
      <radialGradient id="rs-glow-orange"><stop offset="0" stopColor="var(--color-orange-200)" stopOpacity=".95" /><stop offset="1" stopColor="var(--color-orange-200)" stopOpacity="0" /></radialGradient>
    </defs>
  )
}

// Landmarks that carry no meaning: trees and rocks, like a game map, in the product's palette.
const TREES = [
  [40, 80, 1], [76, 112, 0.8], [292, 92, 0.9], [330, 560, 1.1], [290, 590, 0.8], [530, 92, 0.9], [560, 120, 0.7],
  [850, 60, 0.85], [1180, 300, 1], [1160, 340, 0.75], [40, 580, 0.9], [470, 180, 0.7], [820, 540, 0.95], [860, 575, 0.7],
  [1185, 600, 0.8], [760, 92, 0.75],
]
const ROCKS = [[230, 580, 1], [505, 440, 0.8], [905, 330, 1], [1180, 230, 0.8], [705, 520, 0.7], [360, 130, 0.7]]

function Tree({ x, y, s, warm }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <ellipse cx="0" cy="22" rx="17" ry="5" fill="var(--color-ink)" opacity=".07" />
      <rect x="-3" y="6" width="6" height="16" rx="3" fill="#D9CBBF" />
      <g className="anim-sway">
        <circle cx="0" cy="-6" r="17" fill={warm ? '#FFD9C2' : 'var(--shrub-2)'} />
        <circle cx="-9" cy="2" r="11" fill={warm ? '#FFCBA8' : 'var(--shrub)'} />
        <circle cx="10" cy="1" r="10" fill={warm ? '#FFCBA8' : 'var(--shrub)'} />
        <circle cx="-6" cy="-13" r="6" fill="#fff" opacity=".45" />
      </g>
    </g>
  )
}

function Rock({ x, y, s }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <ellipse cx="0" cy="6" rx="16" ry="4" fill="var(--color-ink)" opacity=".06" />
      <path d="M-15 5 Q-14 -8 -3 -10 Q10 -12 15 0 Q16 6 10 6 Z" fill="#E1E6EF" />
      <path d="M-8 -6 Q-2 -10 6 -8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" fill="none" opacity=".8" />
    </g>
  )
}

export function Terrain({ night }) {
  return (
    <g>
      <rect x="0" y="0" width={STAGE.w} height={STAGE.h} fill="var(--terrain)" />
      <rect x="0" y="0" width={STAGE.w} height={STAGE.h} fill="url(#rs-dots)" />
      {/* soft patches */}
      <g filter="url(#rs-soft)" opacity=".9">
        <ellipse cx="170" cy="300" rx="190" ry="230" fill="#F4F7FB" />
        <ellipse cx="820" cy="300" rx="170" ry="140" fill="#F4F7FB" />
        <ellipse cx="1060" cy="160" rx="160" ry="110" fill="#F2F6FF" />
        <ellipse cx="1060" cy="460" rx="160" ry="120" fill="#FFF6EF" />
      </g>
      {/* landmarks */}
      {ROCKS.map(([x, y, k], i) => <Rock key={`r${i}`} x={x} y={y} s={k} />)}
      {TREES.map(([x, y, k], i) => <Tree key={`t${i}`} x={x} y={y} s={k} warm={i % 4 === 1} />)}
      {/* drifting cloud shadows: ambient only */}
      <g opacity=".5" style={{ pointerEvents: 'none' }}>
        <g style={{ animation: 'rs-drift 70s linear infinite' }}>
          <ellipse cx="0" cy="130" rx="90" ry="26" fill="#fff" opacity=".6" />
          <ellipse cx="40" cy="118" rx="50" ry="22" fill="#fff" opacity=".6" />
        </g>
        <g style={{ animation: 'rs-drift 95s linear infinite', animationDelay: '-40s' }}>
          <ellipse cx="0" cy="470" rx="110" ry="28" fill="#fff" opacity=".5" />
        </g>
      </g>
      {night && <rect x="0" y="0" width={STAGE.w} height={STAGE.h} fill="var(--color-blue-900)" opacity=".07" />}
    </g>
  )
}

export function House({ x, y, colour, label, mark }) {
  return (
    <g transform={`translate(${x} ${y}) scale(1.3)`}>
      <g filter="url(#rs-shadow)">
        <rect x="-30" y="-12" width="60" height="44" rx="10" fill="#fff" />
        <path d="M-36 -8 L0 -38 L36 -8 Z" fill={colour} stroke={colour} strokeWidth="6" strokeLinejoin="round" />
      </g>
      <path d="M-36 -8 L0 -38 L36 -8" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="2" strokeLinejoin="round" />
      <rect x="-8" y="8" width="16" height="24" rx="5" fill={colour} opacity=".18" />
      <rect x="-23" y="0" width="11" height="10" rx="3" fill="var(--color-blue-100)" />
      <rect x="12" y="0" width="11" height="10" rx="3" fill="var(--color-blue-100)" />
      {mark === 'missed' && <circle cx="26" cy="-14" r="4" fill="var(--color-bad)" />}
    </g>
  )
}

function ZoneTag({ x, y, label, rule, ai, tone }) {
  const w = Math.max(80, label.length * 6.6 + (rule ? 26 : 16))
  return (
    <g transform={`translate(${x - w / 2} ${y})`}>
      <rect width={w} height="22" rx="11" fill={tone === 'orange' ? 'var(--color-orange-500)' : 'var(--color-ink)'} />
      <text x={rule ? 22 : w / 2} y="15" textAnchor={rule ? 'start' : 'middle'} fontSize="11.5" fontWeight="600" fill="#fff">{label}</text>
      {rule && (
        <g transform="translate(12 11) scale(.42)"><Machine colour="#fff" /></g>
      )}
      {ai != null && null}
    </g>
  )
}

/** Inside a zone card: the rule-run role that works there, as a machine. */
function RuleBadge({ x, y, label }) {
  if (!label) return null
  const w = label.length * 5.6 + 44
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-w / 2} y="-11" width={w} height="22" rx="11" fill="#fff" stroke="var(--color-line-2)" />
      <g transform={`translate(${-w / 2 + 13} 0) scale(.5)`}><Machine colour="var(--staff-1)" /></g>
      <text x={-w / 2 + 26} y="3.5" fontSize="9.5" fill="var(--color-ink-2)">{label} · <tspan className="font-mono" fill="var(--color-ink-3)">rules</tspan></text>
    </g>
  )
}

/** A rule-run role shown as a machine with its role name: "run by rules, not AI". */
export function RulePost({ x, y, label }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <Machine colour="var(--staff-1)" scale={0.9} />
      <text x="0" y="30" textAnchor="middle" fontSize="10.5" fill="var(--color-ink-2)">{label}</text>
      <text x="0" y="42" textAnchor="middle" fontSize="9" className="font-mono" fill="var(--color-ink-3)">RULES</text>
    </g>
  )
}

export function DutyBuilding({ zone, cancelled, missedCount, active, ruleLabel }) {
  const { x, y, w, h, label } = zone
  return (
    <g transform={`translate(${x} ${y}) scale(1.3)`}>
      {active && <ellipse cx="0" cy="10" rx={w * 0.75} ry={h * 0.7} fill="url(#rs-glow-blue)" />}
      <g filter="url(#rs-shadow)">
        <rect x={-w / 2} y={-h / 2} width={w} height={h} rx="22" fill="var(--glass-strong)" stroke="#fff" strokeWidth="2" />
      </g>
      {/* roof band and columns */}
      <rect x={-w / 2 + 14} y={-h / 2 + 14} width={w - 28} height="22" rx="11" fill="url(#rs-roof)" />
      {[-48, -16, 16, 48].map((cx) => (
        <rect key={cx} x={cx - 7} y={-h / 2 + 46} width="14" height="44" rx="5" fill="var(--color-blue-100)" />
      ))}
      <rect x="-16" y={h / 2 - 34} width="32" height="34" rx="8" fill="var(--color-blue-600)" opacity=".85" />
      <ZoneTag x={0} y={-h / 2 - 32} label={label} />
      <RuleBadge x={0} y={h / 2 + 18} label={ruleLabel} />
      {cancelled && (
        <g transform={`translate(0 ${-4}) rotate(-8)`} className="svg-pop">
          <rect x="-58" y="-16" width="116" height="32" rx="8" fill="#fff" stroke="var(--color-orange-500)" strokeWidth="2.5" />
          <text x="0" y="6" textAnchor="middle" fontSize="14" fontWeight="700" fill="var(--color-orange-700)" letterSpacing="2">CANCELLED</text>
        </g>
      )}
      {missedCount > 0 && !cancelled && (
        <g transform={`translate(${w / 2 - 6} ${-h / 2 + 4})`} className="svg-pop">
          <circle r="15" fill="var(--color-orange-500)" />
          <text y="5" textAnchor="middle" fontSize="13" fontWeight="700" fill="#fff">{missedCount}</text>
        </g>
      )}
    </g>
  )
}

export function Desk({ zone, desk, ruleLabel }) {
  const { x, y, w, h, label } = zone
  const cap = desk.capacity
  const shown = cap == null ? 0 : Math.min(cap, 8)
  const pending = desk.pending || []
  const over = desk.over || (cap != null && pending.length > cap)
  const slotW = 22
  const startX = -((Math.max(shown, 1) - 1) * (slotW + 6)) / 2
  return (
    <g transform={`translate(${x} ${y}) scale(1.22)`}>
      {over && <ellipse cx="0" cy="0" rx={w * 0.8} ry={h * 0.85} fill="url(#rs-glow-orange)" />}
      <g filter="url(#rs-shadow)">
        <rect x={-w / 2} y={-h / 2} width={w} height={h} rx="22" fill="var(--glass-strong)" stroke={over ? 'var(--color-orange-400)' : '#fff'} strokeWidth="2" />
      </g>
      <ZoneTag x={0} y={-h / 2 - 32} label={label} tone={over ? 'orange' : undefined} />
      <RuleBadge x={0} y={h / 2 + 18} label={ruleLabel} />
      <text x={-w / 2 + 16} y={-h / 2 + 24} fontSize="10.5" className="font-mono" fill="var(--color-ink-3)">CAPACITY {cap ?? '—'}{cap != null && cap > 8 ? ` (8 shown)` : ''}</text>
      {/* capacity slots */}
      {Array.from({ length: shown }).map((_, i) => {
        const filled = i < pending.length
        return (
          <g key={i} transform={`translate(${startX + i * (slotW + 6)} -2)`}>
            <rect x={-slotW / 2} y="-14" width={slotW} height="28" rx="6" fill={filled ? '#fff' : 'var(--color-mist)'} stroke={filled ? 'var(--color-blue-400)' : 'var(--color-line-2)'} strokeDasharray={filled ? undefined : '3 3'} />
            {filled && <><path d="M-6 -6 h12 M-6 0 h12 M-6 6 h7" stroke="var(--color-blue-400)" strokeWidth="1.6" strokeLinecap="round" />
              <text y="27" textAnchor="middle" fontSize="9" className="font-mono" fill="var(--color-ink-3)">{pending[i]}</text></>}
          </g>
        )
      })}
      {cap === 0 && <text x="0" y="4" textAnchor="middle" fontSize="12" fill="var(--color-orange-700)">No capacity</text>}
      {/* overflow: requests beyond capacity wait outside */}
      {pending.slice(shown).map((r, i) => (
        <g key={r} transform={`translate(${-w / 2 - 24 - i * 8} ${-10 + i * 8})`} className="svg-pop">
          <rect x="-11" y="-14" width="22" height="28" rx="6" fill="#fff" stroke="var(--color-orange-500)" strokeWidth="2" />
          <text y="4" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="var(--color-orange-700)">{r}</text>
        </g>
      ))}
      {/* just decided */}
      <g transform={`translate(${-w / 2 + 18} ${h / 2 - 18})`}>
        {(desk.decided || []).slice(-4).map((d, i) => (
          <g key={d.id + i} transform={`translate(${i * 46} 0)`} className="svg-pop">
            <rect x="-4" y="-10" width="42" height="20" rx="10" fill={d.decision === 'approved' ? 'var(--color-ok-50)' : 'var(--color-bad-50)'} />
            <text x="17" y="4" textAnchor="middle" fontSize="10" fontWeight="600" fill={d.decision === 'approved' ? 'var(--color-ok)' : 'var(--color-bad)'}>{d.decision === 'approved' ? '✓' : '✕'} {d.id}</text>
          </g>
        ))}
      </g>
      {desk.capacityNote && (
        <g transform={`translate(${w / 2 - 10} ${-h / 2 - 2})`}>
          <rect x="-96" y="-12" width="100" height="22" rx="11" fill="var(--color-orange-50)" stroke="var(--color-orange-200)" />
          <text x="-46" y="3" textAnchor="middle" fontSize="10.5" fontWeight="600" fill="var(--color-orange-700)">capacity {desk.capacityNote.from ?? '?'} → {desk.capacityNote.to}</text>
        </g>
      )}
    </g>
  )
}

export function Gate({ zone, results, ruleLabel }) {
  const { x, y, label } = zone
  const pass = results.filter((r) => r.badge === 'pass').length
  const fail = results.filter((r) => r.badge === 'fail').length
  const warn = results.filter((r) => r.badge === 'warn').length
  return (
    <g transform={`translate(${x} ${y}) scale(1.22)`}>
      {fail > 0 && <ellipse cx="0" cy="10" rx="150" ry="100" fill="url(#rs-glow-orange)" />}
      <g filter="url(#rs-shadow)">
        <rect x="-86" y="-58" width="20" height="104" rx="8" fill="#fff" />
        <rect x="66" y="-58" width="20" height="104" rx="8" fill="#fff" />
        <rect x="-96" y="-72" width="192" height="26" rx="13" fill="url(#rs-roof)" />
      </g>
      <g transform="translate(70 -72)">
        <path d="M0 0 V-36" stroke="var(--color-ink)" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M0 -36 h26 l-6 8 6 8 h-26 z" fill="url(#rs-orange)" className="anim-sway" />
      </g>
      <text x="-6" y="-55" textAnchor="middle" fontSize="12" fontWeight="600" fill="#fff">{label}</text>
      {/* the line people cross at the check */}
      <path d="M-66 30 H66" stroke="var(--color-line-2)" strokeWidth="3" strokeDasharray="6 6" />
      {results.length > 0 && (
        <g transform="translate(0 -18)">
          <rect x="-58" y="-14" width="116" height="28" rx="14" fill="#fff" stroke="var(--color-line)" />
          <text x="0" y="5" textAnchor="middle" fontSize="12" fontWeight="600">
            <tspan fill="var(--color-ok)">✓ {pass}</tspan>
            {warn > 0 && <tspan dx="8" fill="var(--color-orange-700)">! {warn}</tspan>}
            <tspan dx="8" fill="var(--color-bad)">✕ {fail}</tspan>
          </text>
        </g>
      )}
      <RuleBadge x={0} y={10} label={ruleLabel} />
    </g>
  )
}

function HazardIcon({ text }) {
  const t = (text || '').toLowerCase()
  if (/storm|rain|flood|monsoon|weather/.test(t)) {
    return (
      <g>
        <ellipse cx="-6" cy="-4" rx="12" ry="9" fill="#fff" /><ellipse cx="6" cy="-6" rx="11" ry="10" fill="#fff" /><ellipse cx="0" cy="0" rx="16" ry="8" fill="#fff" />
        {[-8, 0, 8].map((x) => <path key={x} d={`M${x} 10 l-3 7`} stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />)}
      </g>
    )
  }
  if (/train|rail|metro/.test(t)) {
    return (
      <g>
        <rect x="-12" y="-13" width="24" height="22" rx="6" fill="#fff" />
        <rect x="-8" y="-9" width="16" height="7" rx="2" fill="var(--color-orange-500)" />
        <circle cx="-6" cy="4" r="2" fill="var(--color-orange-500)" /><circle cx="6" cy="4" r="2" fill="var(--color-orange-500)" />
        <path d="M-9 13 l-4 5 M9 13 l4 5" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </g>
    )
  }
  if (/bus|road|traffic|accident|strike|transport/.test(t)) {
    return (
      <g>
        <path d="M0 -15 L11 12 H-11 Z" fill="#fff" />
        <path d="M-5 0 H5 M-7.5 6 H7.5" stroke="var(--color-orange-500)" strokeWidth="2.6" />
      </g>
    )
  }
  return <g><path d="M0 -14 L13 11 H-13 Z" fill="#fff" /><path d="M0 -4 v6 M0 6 v.1" stroke="var(--color-orange-500)" strokeWidth="2.6" strokeLinecap="round" /></g>
}

export function Hazard({ x, y, hazard, words }) {
  const label = `${hazard.text}${hazard.delay ? ` · +${hazard.delay} min` : ''}`
  const w = Math.min(252, Math.min(36, label.length) * 6.4 + 24)
  return (
    <g transform={`translate(${x} ${y}) scale(1.4)`} className="svg-pop">
      <circle r="30" fill="var(--color-orange-500)" opacity=".25" className="anim-pulse" />
      <circle r="26" fill="url(#rs-orange)" stroke="#fff" strokeWidth="3" />
      <HazardIcon text={hazard.text} />
      <g transform={`translate(${-w / 2} 34)`}>
        <rect width={w} height="24" rx="12" fill="#fff" stroke="var(--color-orange-200)" />
        <text x={w / 2} y="16" textAnchor="middle" fontSize="11.5" fontWeight="600" fill="var(--color-orange-700)">{label.length > 36 ? label.slice(0, 35) + '…' : label}</text>
      </g>
      {hazard.people?.length > 0 && words && (
        <text x="0" y="74" textAnchor="middle" fontSize="10" className="font-mono" fill="var(--color-ink-3)">affects {hazard.people.join(', ')}</text>
      )}
    </g>
  )
}

export function Commons({ zone }) {
  if (!zone.staff.length) return null
  const w = zone.staff.length * 56 + 44
  return (
    <g transform={`translate(${zone.x} ${zone.y})`}>
      <g filter="url(#rs-shadow)"><rect x={-w / 2} y="-34" width={w} height="74" rx="20" fill="var(--glass)" stroke="#fff" /></g>
      <text x="0" y="56" textAnchor="middle" fontSize="10" className="font-mono" fill="var(--color-ink-3)">{zone.label.toUpperCase()}</text>
    </g>
  )
}
