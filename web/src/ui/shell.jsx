// The application shell (Wattbank): a translucent app window floating on the colour field,
// a see-through sidebar, and a frosted content panel. Plus the page header and workflow line.
import { useState } from 'react'
import { cx } from './primitives.jsx'
import { IconAnalysis, IconCheck, IconMenu, IconOverview, IconRuns, IconSetup, IconSim, IconX } from './icons.jsx'
import { href } from '../lib/router.js'
import { useHealth } from '../lib/hooks.js'
import { useSession } from '../lib/session.js'

export function Wordmark({ className }) {
  return (
    <a href={href('/')} className={cx('flex items-center gap-2.5', className)} aria-label="RuleStorm home">
      <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden>
        <rect x="3" y="5" width="26" height="24" rx="11" fill="var(--color-blue-600)" />
        <ellipse cx="11" cy="11" rx="5" ry="2.5" fill="#fff" opacity=".35" />
        <circle cx="12" cy="17" r="2.6" fill="#fff" /><circle cx="20" cy="17" r="2.6" fill="#fff" />
        <circle cx="12.6" cy="17.4" r="1.2" fill="var(--color-ink)" /><circle cx="20.6" cy="17.4" r="1.2" fill="var(--color-ink)" />
        <path d="M22 5.5 L24 2.5" stroke="var(--color-ink)" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="24.5" cy="2.5" r="2.2" fill="var(--color-orange-500)" />
      </svg>
      <div className="leading-tight">
        <div className="text-[18px] font-semibold tracking-tight">RuleStorm</div>
        <div className="text-[11px] text-ink-2">Simulate before rollout</div>
      </div>
    </a>
  )
}

function NavItem({ to, icon: Icon, label, sub, active, onClick }) {
  return (
    <a href={href(to)} onClick={onClick} aria-current={active ? 'page' : undefined}
      className={cx('group flex items-center gap-3 rounded-2xl px-3.5 py-2.5 transition',
        active ? 'bg-white/90 shadow-[0_8px_24px_-14px_rgba(20,34,80,.35)] text-ink' : 'text-ink-2 hover:bg-white/45 hover:text-ink')}>
      <Icon className={cx(active ? 'text-ink' : 'text-ink-3 group-hover:text-ink-2')} />
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-medium">{label}</span>
        {sub && <span className="block truncate font-mono text-[10.5px] text-ink-3">{sub}</span>}
      </span>
    </a>
  )
}

function SidebarBody({ route, onClose }) {
  const s = useSession()
  const ok = useHealth()
  const runId = s.runId || 'demo'
  const items = [
    { to: '/', icon: IconOverview, label: 'Overview', match: ['home'] },
    { to: s.blueprintId ? `/blueprint/${s.blueprintId}` : '/setup', icon: IconSetup, label: 'Setup', sub: s.blueprintId ? `blueprint ${s.blueprintId}` : 'policy · blueprint', match: ['setup', 'review'] },
    { to: `/run/${runId}`, icon: IconSim, label: 'Simulation', sub: `run ${runId}`, match: ['simulation'] },
    { to: `/run/${runId}/analysis`, icon: IconAnalysis, label: 'Analysis', sub: 'findings · evidence', match: ['analysis'] },
  ]
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-1.5 pt-1.5 pb-6">
        <Wordmark />
        {onClose && <button className="lg:hidden p-1.5 rounded-full hover:bg-white/60" onClick={onClose} aria-label="Close menu"><IconX /></button>}
      </div>
      <div className="eyebrow !text-[10px] px-3.5 mb-2">Workspace</div>
      <nav className="flex flex-col gap-1" aria-label="Sections">
        {items.map((it) => <NavItem key={it.label} {...it} active={it.match.includes(route.name)} onClick={onClose} />)}
      </nav>
      <div className="eyebrow !text-[10px] px-3.5 mt-6 mb-2">Library</div>
      <nav className="flex flex-col gap-1" aria-label="Library">
        <NavItem to="/runs" icon={IconRuns} label="Runs" sub="open any run by ID" active={route.name === 'runs'} onClick={onClose} />
      </nav>
      <div className="mt-auto flex flex-col gap-3 pt-6">
        <div className="rounded-2xl bg-white/40 border border-white/60 p-3.5">
          <div className="text-[12.5px] font-medium">Simulation, not prediction</div>
          <p className="text-[12px] leading-snug text-ink-2 mt-1">It explores possible responses in a simulation; it does not predict what a real college will do.</p>
        </div>
        <div role="status" aria-live="polite"
          className={cx('inline-flex items-center gap-2 self-start h-8 px-3 rounded-full border text-[12px] font-medium bg-white/60',
            ok == null ? 'border-white text-ink-3' : ok ? 'border-ok/30 text-ok' : 'border-bad/30 text-bad')}>
          <span className={cx('w-2 h-2 rounded-full', ok == null ? 'bg-ink-4' : ok ? 'bg-ok' : 'bg-bad')} />
          {ok == null ? 'Checking the server…' : ok ? 'Server ready' : 'Server unreachable'}
        </div>
      </div>
    </div>
  )
}

export const JOURNEY = [
  { n: 1, id: 'setup', label: 'Setup', sub: 'Describe the policy' },
  { n: 2, id: 'review', label: 'Review', sub: 'Check facts vs assumptions' },
  { n: 3, id: 'simulate', label: 'Simulate', sub: 'Watch the term unfold' },
  { n: 4, id: 'analyse', label: 'Analyse', sub: 'Find and fix what broke' },
]

/** Where you are in the workflow: one slim line, no boxes. */
export function Stepper({ current, recorded, className }) {
  return (
    <ol className={cx('flex items-center gap-2 sm:gap-3 flex-wrap', className)} aria-label="Workflow">
      {JOURNEY.map((s, i) => {
        const done = s.n < current
        const now = s.n === current
        return (
          <li key={s.id} aria-current={now ? 'step' : undefined} className="flex items-center gap-2 sm:gap-3">
            <span className="flex items-center gap-2">
              <span className={cx('grid place-items-center w-6 h-6 shrink-0 rounded-full text-[11px] font-semibold font-mono transition',
                done ? 'bg-blue-600 text-white' : now ? 'bg-ink text-white ring-4 ring-white/70' : 'bg-white/60 text-ink-3 border border-white')}>
                {done ? <IconCheck size={13} /> : s.n}
              </span>
              <span className={cx('text-[13px]', now ? 'font-semibold text-ink' : done ? 'hidden sm:inline text-ink-2' : 'hidden sm:inline text-ink-3')}>{s.label}</span>
              {now && <span className="hidden md:inline text-[12px] text-ink-3">· {s.sub}</span>}
              {done && recorded && s.n < 3 && <span className="hidden md:inline text-[11.5px] text-ink-3">(recorded run)</span>}
            </span>
            {i < JOURNEY.length - 1 && <span className={cx('h-px w-4 sm:w-10', done ? 'bg-blue-600' : 'bg-ink-4/50')} aria-hidden />}
          </li>
        )
      })}
    </ol>
  )
}

/**
 * The same header on every screen: workflow line, mono eyebrow, title, one sentence, meta,
 * and the one primary action, with a line saying what happens when you take it.
 */
export function PageHeader({ step, recorded, eyebrow, title, subtitle, actions, actionHint, meta }) {
  return (
    <header className="flex flex-col gap-5 mb-7 anim-rise">
      {step && <Stepper current={step} recorded={recorded} />}
      <div className="flex flex-col lg:flex-row lg:items-end gap-5 justify-between">
        <div className="min-w-0">
          <div className="eyebrow mb-2 flex items-center gap-3"><span className="w-6 h-px bg-ink-3/60" />{eyebrow}</div>
          <h1 className="text-[28px] sm:text-[34px] leading-[1.08] font-semibold tracking-[-0.02em] text-ink">{title}</h1>
          {subtitle && <p className="mt-2 text-[14.5px] text-ink-2 max-w-2xl">{subtitle}</p>}
          {meta && <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {actions && (
          <div className="flex flex-col items-start lg:items-end gap-2 shrink-0">
            <div className="flex flex-wrap items-center gap-2">{actions}</div>
            {actionHint && <p className="text-[12px] text-ink-3 max-w-[300px] lg:text-right">{actionHint}</p>}
          </div>
        )}
      </div>
    </header>
  )
}

export function AppLayout({ route, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative min-h-full">
      <div className="app-backdrop" />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 bg-white px-3 py-2 rounded-lg">Skip to content</a>
      {/* phone: a drawer */}
      <div className={cx('fixed inset-0 z-30 bg-ink/20 backdrop-blur-sm lg:hidden', open ? 'block' : 'hidden')} onClick={() => setOpen(false)} aria-hidden />
      <aside className={cx('lg:hidden glass-frame fixed z-40 top-2 bottom-2 left-2 w-[260px] rounded-[28px] p-4 transition-transform', open ? 'translate-x-0' : '-translate-x-[110%]')}>
        <SidebarBody route={route} onClose={() => setOpen(false)} />
      </aside>

      <div className="relative z-10 p-2 sm:p-3 lg:p-4 min-h-screen">
        <div className="glass-frame rounded-[32px] min-h-[calc(100vh-2rem)] flex">
          <aside className="hidden lg:block w-[252px] shrink-0 p-4">
            <div className="sticky top-4 h-[calc(100vh-4rem)]"><SidebarBody route={route} /></div>
          </aside>
          <div className="flex-1 min-w-0 p-2 lg:p-3 lg:pl-0">
            <div className="lg:hidden flex items-center justify-between px-3 h-14">
              <Wordmark />
              <button className="p-2 rounded-full hover:bg-white/60" onClick={() => setOpen(true)} aria-label="Open menu"><IconMenu /></button>
            </div>
            <main id="main" className="glass-panel rounded-[26px] min-h-full px-4 sm:px-6 lg:px-9 py-6 lg:py-8">
              <div className="max-w-[1320px] mx-auto">{children}</div>
            </main>
          </div>
        </div>
      </div>
    </div>
  )
}
