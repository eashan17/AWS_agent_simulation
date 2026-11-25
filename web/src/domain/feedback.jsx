// Waiting and error states shared by every screen.
import { Banner, Button, Card, Spinner } from '../ui/primitives.jsx'
import { IconAlert } from '../ui/icons.jsx'
import { Pebble } from '../sim/Agent.jsx'
import { explain } from '../lib/api.js'
import { navigate } from '../lib/router.js'

/** Pebbles gathering round a table while a slow call works. */
export function Gathering({ colours = ['var(--p1)', 'var(--p2)', 'var(--p3)', 'var(--p4)', 'var(--staff-1)'], className }) {
  return (
    <svg viewBox="-160 -70 320 140" className={className} aria-hidden>
      <ellipse cx="0" cy="24" rx="70" ry="16" fill="var(--color-blue-100)" />
      <rect x="-34" y="4" width="68" height="16" rx="8" fill="#fff" stroke="var(--color-line-2)" />
      <g style={{ transformOrigin: '0 10px', animation: 'rs-spin 9s linear infinite' }}>
        {colours.map((c, i) => {
          const a = (i / colours.length) * Math.PI * 2
          return (
            <g key={i} transform={`translate(${Math.cos(a) * 104} ${Math.sin(a) * 32 + 8})`}>
              <g style={{ animation: 'rs-spin 9s linear infinite reverse', transformBox: 'fill-box', transformOrigin: 'center' }}>
                <g className="anim-float" style={{ animationDelay: `${i * 0.3}s` }}><Pebble colour={c} mood="think" scale={0.9} /></g>
              </g>
            </g>
          )
        })}
      </g>
    </svg>
  )
}

export function WaitingState({ seconds, title, sentence, max = 65 }) {
  return (
    <Card className="flex flex-col items-center text-center py-10" aria-live="polite">
      <Gathering className="w-[320px] max-w-full h-auto" />
      <div className="mt-4 eyebrow">Working · {seconds} s</div>
      <h3 className="mt-2 text-[18px] font-semibold">{title}</h3>
      <p className="mt-1.5 text-[14px] text-ink-2 max-w-md">{sentence}</p>
      <div className="mt-5 w-64 h-1.5 rounded-full bg-white border border-line overflow-hidden">
        <div className="h-full bg-blue-600 transition-all duration-500" style={{ width: `${Math.min(100, (seconds / max) * 100)}%` }} />
      </div>
    </Card>
  )
}

/** An API error in plain words, with what to do next. 409 with a run_id offers "Watch it". */
export function ApiErrorBanner({ error, context, onRetry, retryLabel = 'Try again', className }) {
  if (!error) return null
  const msg = explain(error, context)
  const running = error.kind === 'conflict' && error.body?.run_id
  return (
    <Banner tone={error.kind === 'input' ? 'orange' : 'bad'} icon={<IconAlert size={16} />} className={className}
      title={msg}
      action={running
        ? <Button size="sm" variant="primary" onClick={() => navigate(`/run/${error.body.run_id}`)}>Watch it</Button>
        : error.kind === 'notfound' ? <Button size="sm" onClick={() => navigate('/')}>Go to the overview</Button>
        : onRetry && error.kind !== 'limit' && error.kind !== 'input' ? <Button size="sm" onClick={onRetry}>{retryLabel}</Button> : null}>
      {running ? <>Only one simulation runs at a time, for everyone. Run <span className="font-mono">{error.body.run_id}</span> is going now.</> : null}
    </Banner>
  )
}

export function LoadingBlock({ label = 'Loading…' }) {
  return <div className="flex items-center gap-2 text-[13px] text-ink-3 py-8 justify-center"><Spinner /> {label}</div>
}
