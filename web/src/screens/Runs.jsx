// Runs: open any stored run by its ID, and the runs opened in this browser.
import { Card, CardTitle, IdTag, LinkButton } from '../ui/primitives.jsx'
import { PageHeader } from '../ui/shell.jsx'
import { IconArrow } from '../ui/icons.jsx'
import { OpenById } from './Home.jsx'
import { href } from '../lib/router.js'
import { useSession } from '../lib/session.js'

export default function Runs() {
  const s = useSession()
  const recent = s.recent?.length ? s.recent : ['demo']
  return (
    <div>
      <PageHeader eyebrow="Runs" title="Open a run" subtitle="Every run keeps its ID. Open one to replay it on the map and see its findings and evidence." />
      <div className="grid lg:grid-cols-[1fr_1.3fr] gap-4 items-start">
        <Card><OpenById /></Card>
        <Card>
          <CardTitle title="Recently opened" sub="In this browser" />
          <ul className="flex flex-col divide-y divide-line">
            {recent.map((id) => (
              <li key={id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-2"><IdTag id={id} label="Run" />{id === 'demo' && <span className="text-[12px] text-ink-3">the recorded demo run</span>}{s.runId === id && <span className="text-[12px] text-blue-700">current</span>}</div>
                <div className="flex gap-2">
                  <LinkButton size="sm" href={href(`/run/${id}`)}>Map</LinkButton>
                  <LinkButton size="sm" variant="primary" href={href(`/run/${id}/analysis`)} iconRight={<IconArrow size={14} />}>Analysis</LinkButton>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
