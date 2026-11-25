// Time, shown as time: a flat ruler of the term (periods with their steps as ticks) and a
// playhead that moves as the run plays. The map never encodes time; this does.
import { cx } from '../ui/primitives.jsx'

/**
 * position: continuous, in periods (e.g. 4.5 = halfway through period 5); null = static view.
 * disruptions: {period: n} · highlights: {period: true|n} · checkpoint: period number.
 */
export default function TimeRuler({ periods, stepsPerPeriod = 1, position = null, checkpoint, disruptions = {}, highlights = {}, label = 'week', stepLabel = 'session', onSeek, className, nowText }) {
  const n = Math.max(1, periods)
  const pctAt = (p) => `${(p / n) * 100}%`
  const pos = position == null ? null : Math.max(0, Math.min(n, position))
  return (
    <div className={cx('select-none', className)}>
      <div className="relative h-11">
        {/* periods */}
        <div className="absolute inset-x-0 top-3 h-5 flex rounded-full overflow-hidden border border-line bg-white/80">
          {Array.from({ length: n }).map((_, i) => {
            const p = i + 1
            const dis = disruptions[p]
            const hl = highlights[p]
            return (
              <button key={p} type="button" disabled={!onSeek} onClick={() => onSeek?.(p)}
                aria-label={`${label} ${p}${p === checkpoint ? ', the check' : ''}${dis ? `, ${dis} disruption${dis > 1 ? 's' : ''}` : ''}`}
                className={cx('relative flex-1 border-r border-line last:border-r-0 transition', onSeek && 'hover:bg-blue-50 cursor-pointer', dis && 'bg-orange-50', hl && 'bg-orange-100')}>
                {/* step ticks */}
                {stepsPerPeriod > 1 && Array.from({ length: stepsPerPeriod - 1 }).map((__, k) => (
                  <span key={k} className="absolute top-1.5 bottom-1.5 w-px bg-line-2" style={{ left: `${((k + 1) / stepsPerPeriod) * 100}%` }} aria-hidden />
                ))}
                {dis > 0 && <span className="absolute left-1/2 -translate-x-1/2 -bottom-[3px] w-0 h-0 border-x-[4px] border-x-transparent border-b-[5px] border-b-orange-500" aria-hidden />}
              </button>
            )
          })}
        </div>
        {/* elapsed */}
        {pos != null && (
          <div className="absolute left-0 top-3 h-5 rounded-l-full bg-blue-600/15 pointer-events-none border-r-0 transition-[width] duration-100" style={{ width: pctAt(pos) }} aria-hidden />
        )}
        {/* checkpoint */}
        {checkpoint != null && (
          <div className="absolute top-0 bottom-0 pointer-events-none" style={{ left: pctAt(checkpoint) }} aria-hidden>
            <div className="absolute -translate-x-1/2 -top-1 px-1.5 h-4 rounded-full bg-orange-500 text-white text-[9.5px] font-semibold leading-4 whitespace-nowrap">check</div>
            <div className="absolute top-3 h-5 w-0.5 -translate-x-1/2 bg-orange-500" />
          </div>
        )}
        {/* playhead */}
        {pos != null && (
          <div className="absolute top-1 bottom-0 pointer-events-none transition-[left] duration-100" style={{ left: pctAt(pos) }} aria-hidden>
            <div className="absolute -translate-x-1/2 top-0.5 w-1 h-8 rounded-full bg-ink shadow-[var(--shadow-pill)]" />
          </div>
        )}
      </div>
      <div className="flex justify-between text-[10.5px] font-mono text-ink-3 mt-0.5 px-0.5">
        {Array.from({ length: n }).map((_, i) => <span key={i} className="flex-1 text-center tabular">{i + 1}</span>)}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 mt-1 text-[11.5px] text-ink-3">
        <span>{label}s{stepsPerPeriod > 1 ? `, ${stepsPerPeriod} ${stepLabel}s each` : ''}</span>
        <span className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-orange-50 border border-orange-200" /> disruption</span>
          {checkpoint != null && <span className="inline-flex items-center gap-1"><span className="w-2.5 h-0.5 bg-orange-500" /> check</span>}
          {nowText && <span className="font-mono text-ink-2">{nowText}</span>}
        </span>
      </div>
    </div>
  )
}
