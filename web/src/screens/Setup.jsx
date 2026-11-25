// S2 Setup: write the rule in plain words; nothing else to configure.
import { useEffect, useRef, useState } from 'react'
import { Button, Card, Chip, TextArea } from '../ui/primitives.jsx'
import { IconArrow, IconCheck } from '../ui/icons.jsx'
import { PageHeader } from '../ui/shell.jsx'
import { ApiErrorBanner, WaitingState } from '../domain/feedback.jsx'
import { api } from '../lib/api.js'
import { primeCache, useElapsed, useTemplates } from '../lib/hooks.js'
import { navigate } from '../lib/router.js'
import { setSession, useSession } from '../lib/session.js'
import { humanize } from '../lib/words.js'

const MAX = 2000

export default function Setup() {
  const s = useSession()
  const templates = useTemplates()
  const [draft, setDraft] = useState(() => s.draft || { text: '', purpose: '', environment: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const saved = useRef(null) // {key, id}: reuse a saved policy if the text hasn't changed
  const seconds = useElapsed(busy)

  // pre-fill with the first template's example the first time
  useEffect(() => {
    if (!s.draft && templates.data?.length && !draft.text && !draft.purpose && !draft.environment) {
      setDraft({ ...templates.data[0].example_input })
    }
  }, [templates.data]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSession({ draft }) }, [draft])

  const set = (k) => (v) => { setDraft((d) => ({ ...d, [k]: v })); setFieldErrors((f) => ({ ...f, [k]: null })) }
  const empty = ['text', 'purpose', 'environment'].filter((k) => !draft[k].trim())

  const build = async () => {
    if (empty.length) {
      setFieldErrors(Object.fromEntries(empty.map((k) => [k, 'Write at least a few words here.'])))
      return
    }
    setBusy(true); setError(null); setFieldErrors({})
    try {
      const key = JSON.stringify(draft)
      let policyId = saved.current?.key === key ? saved.current.id : null
      if (!policyId) {
        const p = await api.savePolicy(draft)
        policyId = p.id
        saved.current = { key, id: policyId }
      }
      const bp = await api.buildBlueprint(policyId)
      primeCache(`blueprint-record:${bp.id}`, bp)
      setSession({ blueprintId: bp.id })
      navigate(`/blueprint/${bp.id}`)
    } catch (err) {
      if (err.kind === 'input' && err.fields) setFieldErrors(err.fields)
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader step={1} eyebrow="New policy" title="Describe the policy"
        subtitle="Write the rule, why it exists and the setting, in plain words. RuleStorm turns it into a simulation you check before anything runs." />

      {busy ? (
        <WaitingState seconds={seconds} title="Building the simulation" sentence="Reading your policy and building the simulation. This takes up to a minute." />
      ) : (
        <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4 items-start">
          <Card>
            <form onSubmit={(e) => { e.preventDefault(); build() }} className="flex flex-col gap-5" noValidate>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] text-ink-3 mr-1">Start from an example:</span>
                {(templates.data || []).map((t) => (
                  <Chip key={t.id} onClick={() => { setDraft({ ...t.example_input }); setFieldErrors({}) }}
                    active={draft.text === t.example_input.text}>Use the {humanize(t.id)} example</Chip>
                ))}
              </div>
              <TextArea id="policy" label="Policy" hint="The rule as it would be written down." value={draft.text} onChange={set('text')} max={MAX} rows={4} error={fieldErrors.text} />
              <TextArea id="purpose" label="Purpose" hint="What the rule is meant to achieve." value={draft.purpose} onChange={set('purpose')} max={MAX} rows={2} error={fieldErrors.purpose} />
              <TextArea id="environment" label="Environment" hint="Who is affected and what the place is like: people, staff, what tends to go wrong." value={draft.environment} onChange={set('environment')} max={MAX} rows={5} error={fieldErrors.environment} />
              <ApiErrorBanner error={error} onRetry={build}
                context={{ limit: "Today's limit for building new simulations is reached. You can still open the demo run and any finished run.", timeout: 'Building took too long. Try again. Each try uses one of the day\'s 50 blueprint requests.' }} />
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <p className="text-[12.5px] text-ink-3">Takes 15–30 seconds. Nothing runs until you approve.</p>
                <Button type="submit" variant="primary" size="lg" iconRight={<IconArrow size={18} />}>Build the simulation</Button>
              </div>
            </form>
          </Card>

          <div className="flex flex-col gap-4">
            <Card>
              <div className="eyebrow mb-3">What happens next</div>
              <ol className="flex flex-col gap-3">
                {[
                  ['RuleStorm picks a model', 'It matches your policy to a template it can simulate, or says it can\'t.'],
                  ['It drafts the values', 'Thresholds, capacity, disruptions and people, each marked as your fact or its assumption.'],
                  ['You review and approve', 'Approval freezes the values; every run uses exactly these.'],
                ].map(([t, d], i) => (
                  <li key={t} className="flex gap-3">
                    <span className="grid place-items-center w-6 h-6 shrink-0 rounded-full bg-blue-50 text-blue-700 text-[11px] font-mono font-semibold">{i + 1}</span>
                    <span><span className="block text-[13.5px] font-medium">{t}</span><span className="block text-[12.5px] text-ink-3">{d}</span></span>
                  </li>
                ))}
              </ol>
            </Card>
            <Card>
              <div className="eyebrow mb-3">What it can model</div>
              <ul className="flex flex-col gap-2">
                {(templates.data || []).map((t) => (
                  <li key={t.id} className="flex gap-2.5 text-[13px]"><IconCheck size={16} className="text-blue-600 shrink-0 mt-0.5" /><span><span className="font-medium">{t.title}</span><span className="block text-ink-3 text-[12.5px]">{t.scope}</span></span></li>
                ))}
                {templates.error && <li className="text-[12.5px] text-ink-3">Couldn't load the list. You can still build.</li>}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
