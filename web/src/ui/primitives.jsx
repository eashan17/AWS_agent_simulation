// Design-system primitives. They know nothing about RuleStorm; every screen is built from them.
import { useState } from 'react'

const cx = (...a) => a.filter(Boolean).join(' ')
export { cx }

/* ---------- Button ----------
   primary: the black pill (one per stage of the journey) · secondary: white glass pill ·
   ghost: text button · quiet: small chip-like button */
export function Button({ variant = 'secondary', size = 'md', icon, iconRight, className, children, ...rest }) {
  const base = 'inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap transition select-none disabled:cursor-not-allowed'
  const sizes = { sm: 'h-8 px-3 text-[13px] rounded-full', md: 'h-10 px-4 text-sm rounded-full', lg: 'h-12 px-6 text-[15px] rounded-full' }
  const variants = {
    primary: 'bg-ink text-white shadow-[var(--shadow-pill)] hover:bg-ink-2 active:translate-y-px disabled:bg-ink-4 disabled:shadow-none',
    secondary: 'bg-white/80 text-ink border border-line hover:bg-white hover:border-line-2 active:translate-y-px disabled:text-ink-4',
    blue: 'bg-blue-600 text-white hover:bg-blue-700 active:translate-y-px disabled:bg-blue-200',
    ghost: 'text-ink-2 hover:text-ink hover:bg-white/60 disabled:text-ink-4',
    quiet: 'bg-mist text-ink-2 hover:bg-blue-50 hover:text-blue-700 disabled:text-ink-4',
  }
  return (
    <button type="button" className={cx(base, sizes[size], variants[variant], className)} {...rest}>
      {icon}
      {children}
      {iconRight}
    </button>
  )
}

export function LinkButton({ href, variant = 'secondary', size = 'md', className, children, icon, iconRight }) {
  const sizes = { sm: 'h-8 px-3 text-[13px]', md: 'h-10 px-4 text-sm', lg: 'h-12 px-6 text-[15px]' }
  const variants = {
    primary: 'bg-ink text-white shadow-[var(--shadow-pill)] hover:bg-ink-2',
    secondary: 'bg-white/80 text-ink border border-line hover:bg-white hover:border-line-2',
    ghost: 'text-ink-2 hover:text-ink hover:bg-white/60',
  }
  return (
    <a href={href} className={cx('inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap transition', sizes[size], variants[variant], className)}>
      {icon}{children}{iconRight}
    </a>
  )
}

/* ---------- Surfaces ---------- */
export function Card({ className, children, pad = true, as: Tag = 'section', ...rest }) {
  return (
    <Tag className={cx('glass rounded-[var(--radius-card)]', pad && 'p-5 sm:p-6', className)} {...rest}>
      {children}
    </Tag>
  )
}

export function CardTitle({ eyebrow, title, sub, action, className, children }) {
  const caption = sub || eyebrow
  return (
    <div className={cx('flex items-start justify-between gap-4 mb-5', className)}>
      <div className="min-w-0">
        {title && <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>}
        {caption && <p className="text-[13px] text-ink-3 mt-0.5">{caption}</p>}
        {children}
      </div>
      {action}
    </div>
  )
}

/* ---------- Badges, chips, dots ---------- */
export function Dot({ tone = 'ink', className }) {
  const tones = { ok: 'bg-ok', bad: 'bg-bad', blue: 'bg-blue-600', orange: 'bg-orange-500', ink: 'bg-ink-3', live: 'bg-blue-600' }
  return (
    <span className={cx('relative inline-flex w-2 h-2 shrink-0', className)}>
      {tone === 'live' && <span className="absolute inset-0 rounded-full bg-blue-600 anim-pulse" />}
      <span className={cx('relative w-2 h-2 rounded-full', tones[tone])} />
    </span>
  )
}

export function Badge({ tone = 'neutral', className, children, title }) {
  const tones = {
    neutral: 'bg-mist text-ink-2 border-line',
    blue: 'bg-blue-50 text-blue-700 border-blue-100',
    orange: 'bg-orange-50 text-orange-700 border-orange-100',
    ok: 'bg-ok-50 text-ok border-transparent',
    bad: 'bg-bad-50 text-bad border-transparent',
    ink: 'bg-ink text-white border-ink',
    glass: 'bg-white/80 text-ink-2 border-white',
  }
  return (
    <span title={title} className={cx('inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full border text-[12px] font-medium whitespace-nowrap', tones[tone], className)}>
      {children}
    </span>
  )
}

export function Chip({ active, onClick, children, count, className, ...rest }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={!!active}
      className={cx(
        'inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-[13px] border transition whitespace-nowrap',
        active ? 'bg-white text-blue-700 border-blue-200 shadow-[var(--shadow-glass)]' : 'bg-transparent text-ink-3 border-line hover:border-line-2 hover:text-ink',
        className,
      )}
      {...rest}
    >
      {children}
      {count != null && <span className={cx('tabular text-[11px] font-mono', active ? 'text-blue-400' : 'text-ink-4')}>{count}</span>}
    </button>
  )
}

/* ---------- IDs: small, mono, copyable ---------- */
export function IdTag({ id, className, label }) {
  const [copied, setCopied] = useState(false)
  if (!id) return null
  const copy = async () => {
    try { await navigator.clipboard.writeText(id); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch { /* no clipboard */ }
  }
  return (
    <button type="button" onClick={copy} title={copied ? 'Copied' : `Copy ${id}`} aria-label={`${label || 'ID'} ${id}, copy`}
      className={cx('inline-flex items-center gap-1 h-6 px-2 rounded-md font-mono text-[11.5px] text-ink-2 bg-white/70 border border-line hover:border-blue-200 hover:text-blue-700 transition', className)}>
      {id}
      <span className="text-ink-4" aria-hidden>{copied ? '✓' : '⧉'}</span>
    </button>
  )
}

/* ---------- Tabs ---------- */
export function Tabs({ tabs, value, onChange, className, size = 'md' }) {
  return (
    <div role="tablist" className={cx('inline-flex w-fit max-w-full overflow-x-auto thin-scroll p-1 gap-1 rounded-full bg-white/35 border border-white/70 backdrop-blur', className)}>
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={value === t.id}
          disabled={t.disabled}
          onClick={() => onChange(t.id)}
          title={t.hint}
          className={cx(
            'inline-flex items-center gap-1.5 rounded-full font-medium transition disabled:text-ink-4 disabled:cursor-not-allowed',
            size === 'sm' ? 'h-7 px-3 text-[12.5px]' : 'h-9 px-4 text-[13.5px]',
            value === t.id ? 'bg-white text-ink shadow-[0_6px_18px_-10px_rgba(20,34,80,.45)]' : 'text-ink-2 hover:text-ink hover:bg-white/60',
          )}
        >
          {t.icon}
          {t.label}
          {t.count != null && <span className={cx('font-mono text-[11px] px-1.5 rounded-full', value === t.id ? 'bg-blue-50 text-blue-700' : 'text-ink-3')}>{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

/* ---------- Stat tile (Wattbank "Total Load": label, light big number, a line of context) ---------- */
export function StatTile({ label, value, unit, sub, tone, className }) {
  return (
    <Card className={cx('!p-5 flex flex-col', className)}>
      <div className="text-[13.5px] font-medium text-ink-2">{label}</div>
      <div className="flex items-baseline gap-1 mt-4">
        <span className="text-[38px] leading-none font-normal tracking-[-0.03em] tabular">{value}</span>
        {unit && <span className="text-[15px] text-ink-3">{unit}</span>}
      </div>
      {sub && <div className={cx('mt-3 text-[12.5px]', tone === 'bad' ? 'text-bad' : tone === 'ok' ? 'text-ok' : 'text-ink-3')}>{sub}</div>}
    </Card>
  )
}

/* ---------- Progress ---------- */
export function Progress({ value, max, tone = 'blue', className, label }) {
  const pctv = max ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className={cx('w-full', className)} role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className="h-2 rounded-full bg-white/80 border border-line overflow-hidden">
        <div className={cx('h-full rounded-full transition-all duration-700', tone === 'orange' ? 'bg-orange-500' : 'bg-blue-600')} style={{ width: `${pctv}%` }} />
      </div>
    </div>
  )
}

export function Spinner({ className }) {
  return <span className={cx('inline-block w-4 h-4 rounded-full border-2 border-current border-r-transparent anim-spin', className)} aria-hidden />
}

/* ---------- Messages ---------- */
export function Banner({ tone = 'blue', icon, title, children, action, className }) {
  const tones = {
    blue: 'bg-white/70 border-white text-ink [&_.bn-title]:text-blue-700 [&_.bn-icon]:text-blue-600',
    orange: 'bg-white/70 border-white text-ink [&_.bn-title]:text-orange-700 [&_.bn-icon]:text-orange-500',
    bad: 'bg-white/75 border-white text-ink [&_.bn-title]:text-bad [&_.bn-icon]:text-bad',
    ok: 'bg-white/70 border-white text-ink [&_.bn-title]:text-ok [&_.bn-icon]:text-ok',
    ink: 'bg-ink text-white border-ink',
    glass: 'bg-white/60 border-white text-ink-2',
  }
  return (
    <div role={tone === 'bad' ? 'alert' : 'status'} className={cx('flex items-start gap-3 rounded-2xl border px-4 py-3 text-[13.5px] backdrop-blur-md shadow-[0_10px_30px_-20px_rgba(20,34,80,.4)]', tones[tone], className)}>
      {icon && <span className="bn-icon mt-0.5 shrink-0" aria-hidden>{icon}</span>}
      <div className="min-w-0 flex-1">
        {title && <div className="bn-title font-semibold">{title}</div>}
        {children && <div className={cx(title && 'mt-0.5', 'text-ink-2')}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function EmptyState({ icon, title, children, action, className }) {
  return (
    <div className={cx('flex flex-col items-center text-center py-12 px-6', className)}>
      {icon && <div className="mb-4">{icon}</div>}
      <h3 className="text-[17px] font-semibold">{title}</h3>
      {children && <p className="mt-1.5 text-[14px] text-ink-2 max-w-md">{children}</p>}
      {action && <div className="mt-5 flex flex-wrap gap-2 justify-center">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cx('skeleton rounded-xl', className)} />
}

/* ---------- Form field with live counter ---------- */
export function TextArea({ id, label, hint, value, onChange, max = 2000, rows = 4, error, disabled, placeholder }) {
  const n = value.length
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label htmlFor={id} className="text-[13.5px] font-medium text-ink">{label}</label>
        <span className={cx('font-mono text-[11px] tabular', n >= max ? 'text-orange-700' : 'text-ink-3')} aria-live="polite">{n.toLocaleString()} / {max.toLocaleString()}</span>
      </div>
      {hint && <p id={`${id}-hint`} className="text-[12.5px] text-ink-3 mb-2">{hint}</p>}
      <textarea
        id={id}
        rows={rows}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        aria-describedby={[hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(' ') || undefined}
        aria-invalid={!!error}
        onChange={(e) => onChange(e.target.value.slice(0, max))}
        className={cx(
          'w-full resize-y rounded-2xl border bg-white/85 px-4 py-3 text-[14px] leading-relaxed text-ink placeholder:text-ink-4 transition',
          'focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-400 disabled:opacity-60',
          error ? 'border-bad' : 'border-line',
        )}
      />
      {error && <p id={`${id}-err`} className="mt-1.5 text-[12.5px] text-bad">{error}</p>}
    </div>
  )
}

export function Kbd({ children }) {
  return <kbd className="font-mono text-[11px] px-1.5 py-0.5 rounded border border-line bg-white text-ink-3">{children}</kbd>
}
