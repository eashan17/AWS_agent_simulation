// Play, pause, scrub and speed for the stage. Keyboard: space plays or pauses.
import { cx, Dot } from '../ui/primitives.jsx'
import { IconPause, IconPlay, IconRestart, IconSkip } from '../ui/icons.jsx'

const SPEEDS = [1, 2, 4, 8]

export default function PlaybackBar({ pb, events, words, live, className }) {
  const n = events.length
  const cur = events[Math.max(0, pb.count - 1)]
  const playing = pb.playing && !pb.atEnd
  return (
    <div className={cx('flex flex-col sm:flex-row sm:items-center gap-3', className)}>
      <div className="flex items-center gap-1.5">
        <button type="button" onClick={() => (pb.atEnd ? pb.restart() : pb.toggle())}
          className="grid place-items-center w-10 h-10 rounded-full bg-ink text-white shadow-[var(--shadow-pill)] hover:bg-ink-2"
          aria-label={playing ? 'Pause' : pb.atEnd ? 'Play again from the start' : 'Play'}>
          {playing ? <IconPause /> : <IconPlay />}
        </button>
        <button type="button" onClick={pb.restart} className="grid place-items-center w-9 h-9 rounded-full bg-white/80 border border-line text-ink-2 hover:text-ink" aria-label="Restart from the start" title="Restart">
          <IconRestart size={16} />
        </button>
        <button type="button" onClick={pb.toEnd} className="grid place-items-center w-9 h-9 rounded-full bg-white/80 border border-line text-ink-2 hover:text-ink" aria-label="Skip to the end" title="Skip to the end">
          <IconSkip size={16} />
        </button>
      </div>
      <div className="flex-1 min-w-0">
        <label className="sr-only" htmlFor="rs-scrub">Position in the run</label>
        <input id="rs-scrub" type="range" min={0} max={Math.max(0, n)} value={Math.min(pb.count, n)}
          onChange={(e) => { const v = Number(e.target.value); if (v === 0) pb.seekIndex(0); else pb.seekIndex(v - 1) }}
          className="w-full accent-[var(--color-blue-600)]" />
        <div className="flex items-center justify-between text-[11.5px] text-ink-3 font-mono mt-0.5">
          <span className="truncate">{cur ? `${words.where(cur.period, cur.step)} · ${cur.event_id}` : 'start of term'}</span>
          <span className="tabular shrink-0 ml-2">{Math.min(pb.count, n)} / {n} events</span>
        </div>
      </div>
      <div className="flex items-center gap-1" role="group" aria-label="Speed">
        {live && <span className="inline-flex items-center gap-1.5 mr-2 text-[12px] font-medium text-blue-700"><Dot tone="live" /> Live</span>}
        {SPEEDS.map((s) => (
          <button key={s} type="button" onClick={() => pb.setSpeed(s)} aria-pressed={pb.speed === s}
            className={cx('h-8 min-w-9 px-2 rounded-full text-[12px] font-mono border transition', pb.speed === s ? 'bg-ink text-white border-ink' : 'bg-white/70 text-ink-2 border-line hover:text-ink')}>
            {s}×
          </button>
        ))}
      </div>
    </div>
  )
}
