// The map's clock: time shown as time passing. "Week 5 of 10 · Session 9", with a ring that
// sweeps as the current step plays out. Sits in the map's top-left corner as a glass card.
import { cap } from '../lib/words.js'

export default function Clock({ clock, words }) {
  if (!clock) return null
  const r = 17
  const c = 2 * Math.PI * r
  const frac = Math.max(0, Math.min(1, clock.frac || 0))
  const big = clock.period ? `${cap(words.period)} ${clock.period} of ${words.periods}` : 'Start of term'
  const small = !clock.period ? 'press play' : clock.step == null ? `End of ${words.period}` : `${cap(words.step)} ${clock.step}`
  const w = Math.max(178, big.length * 8.6 + 70)
  return (
    <g transform="translate(16 16) scale(1.45)" aria-hidden>
      <g filter="url(#rs-shadow)"><rect width={w} height="58" rx="18" fill="var(--glass-strong)" stroke="#fff" /></g>
      <g transform="translate(29 29)">
        <circle r={r} fill="none" stroke="var(--color-line)" strokeWidth="4" />
        <circle r={r} fill="none" stroke={clock.step == null && clock.period ? 'var(--color-orange-500)' : 'var(--color-blue-600)'} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${c * frac} ${c}`} transform="rotate(-90)" />
        {/* the hand */}
        <line x1="0" y1="0" x2={Math.sin(frac * 2 * Math.PI) * (r - 6)} y2={-Math.cos(frac * 2 * Math.PI) * (r - 6)} stroke="var(--color-ink)" strokeWidth="2" strokeLinecap="round" />
        <circle r="2.2" fill="var(--color-ink)" />
      </g>
      <text x="58" y="26" fontSize="14" fontWeight="600" fill="var(--color-ink)">{big}</text>
      <text x="58" y="44" fontSize="11.5" className="font-mono" fill="var(--color-ink-3)">{small}</text>
    </g>
  )
}
