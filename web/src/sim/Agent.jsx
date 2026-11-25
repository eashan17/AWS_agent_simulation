// The "pebble" mascot. One drawing for every person: on the stage (inside an animated group)
// and in the workspace as an avatar, so the same person looks the same everywhere.

/**
 * Pebble: drawn around (0, 0), about 30 px tall at scale 1.
 * mood: idle | think | say | refused | stuck | happy | sad
 * ai: false draws a rule-run "machine" (square body, gear) instead of a pebble.
 */
export function Pebble({ colour, mood = 'idle', scale = 1, ai = true, initial, pupils = 0 }) {
  if (!ai) return <Machine colour={colour} scale={scale} />
  const eyeY = mood === 'sad' ? 1 : 0
  return (
    <g transform={`scale(${scale})`}>
      <ellipse cx="0" cy="15.5" rx="11" ry="3.2" fill="var(--color-ink)" opacity=".12" />
      <g className="pebble-body">
        {/* antenna */}
        <path d="M5 -14 Q 7 -19 9.5 -20" stroke="var(--color-ink)" strokeWidth="1.4" fill="none" strokeLinecap="round" />
        <circle cx="10" cy="-20.5" r="2.4" fill={mood === 'refused' ? 'var(--color-bad)' : 'var(--color-orange-500)'} />
        {/* body */}
        <rect x="-13" y="-15" width="26" height="28" rx="12" fill={colour} />
        <ellipse cx="-5" cy="-8" rx="6" ry="3.2" fill="#fff" opacity=".32" />
        {/* cheeks */}
        <circle cx="-8" cy="4" r="2.2" fill="#fff" opacity=".22" />
        <circle cx="8" cy="4" r="2.2" fill="#fff" opacity=".22" />
        {/* eyes */}
        <g className="anim-blink">
          <circle cx="-4.6" cy={-1 + eyeY} r="3.1" fill="#fff" />
          <circle cx="4.6" cy={-1 + eyeY} r="3.1" fill="#fff" />
          <g data-pupils transform={`translate(${pupils} 0)`}>
            <circle cx="-4.6" cy={-0.6 + eyeY} r="1.5" fill="var(--color-ink)" />
            <circle cx="4.6" cy={-0.6 + eyeY} r="1.5" fill="var(--color-ink)" />
          </g>
        </g>
        {/* mouth */}
        {mood === 'happy' && <path d="M-3 6 Q0 9 3 6" stroke="var(--color-ink)" strokeWidth="1.3" fill="none" strokeLinecap="round" />}
        {(mood === 'sad' || mood === 'refused' || mood === 'stuck') && <path d="M-3 8 Q0 5.5 3 8" stroke="var(--color-ink)" strokeWidth="1.3" fill="none" strokeLinecap="round" />}
        {mood === 'say' && <ellipse cx="0" cy="7" rx="2.4" ry="1.8" fill="var(--color-ink)" />}
        {(mood === 'idle' || mood === 'think') && <path d="M-2 7 h4" stroke="var(--color-ink)" strokeWidth="1.3" strokeLinecap="round" />}
      </g>
    </g>
  )
}

/** Rule-run roles (the office, the exam officer, gate security): a small machine, not a person. */
export function Machine({ colour = 'var(--staff-1)', scale = 1 }) {
  return (
    <g transform={`scale(${scale})`}>
      <ellipse cx="0" cy="15.5" rx="11" ry="3" fill="var(--color-ink)" opacity=".1" />
      <rect x="-12" y="-13" width="24" height="26" rx="6" fill="#fff" stroke={colour} strokeWidth="2" />
      <g transform="translate(0 0)" className="anim-spin" style={{ transformBox: 'fill-box', transformOrigin: 'center', animationDuration: '6s' }}>
        <circle cx="0" cy="0" r="5" fill="none" stroke={colour} strokeWidth="2.2" />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
          <rect key={a} x="-1.4" y="-8.6" width="2.8" height="3.4" rx=".8" fill={colour} transform={`rotate(${a})`} />
        ))}
      </g>
    </g>
  )
}

/** Avatar for the workspace (cards, tables, the evidence chain). */
export function PersonAvatar({ colour, size = 36, ai = true, mood = 'idle', className, title }) {
  return (
    <svg width={size} height={size} viewBox="-18 -25 36 44" className={className} role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <Pebble colour={colour} ai={ai} mood={mood} />
    </svg>
  )
}
