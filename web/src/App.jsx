import { useEffect } from 'react'
import { AppLayout } from './ui/shell.jsx'
import { EmptyState, LinkButton } from './ui/primitives.jsx'
import { useRoute, href } from './lib/router.js'
import { setSession } from './lib/session.js'
import Home from './screens/Home.jsx'
import Setup from './screens/Setup.jsx'
import Review from './screens/Review.jsx'
import Simulation from './screens/Simulation.jsx'
import Analysis from './screens/Analysis.jsx'
import Runs from './screens/Runs.jsx'

const TITLES = { home: 'Overview', setup: 'Setup', review: 'Review', simulation: 'Simulation', analysis: 'Analysis', runs: 'Runs' }

export default function App() {
  const route = useRoute()
  useEffect(() => {
    document.title = `${TITLES[route.name] || 'RuleStorm'}${route.id ? ` · ${route.id}` : ''} · RuleStorm`
    if (route.name === 'review') setSession({ blueprintId: route.id })
  }, [route.name, route.id])
  let page
  switch (route.name) {
    case 'home': page = <Home />; break
    case 'setup': page = <Setup />; break
    case 'review': page = <Review key={route.id} id={route.id} tab={route.tab} />; break
    case 'simulation': page = <Simulation key={route.id} id={route.id} />; break
    case 'analysis': page = <Analysis key={route.id} id={route.id} tab={route.tab} arg={route.arg} />; break
    case 'runs': page = <Runs />; break
    default: page = <EmptyState title="This page doesn't exist." action={<LinkButton variant="primary" href={href('/')}>Go to the overview</LinkButton>} />
  }
  return <AppLayout route={route}>{page}</AppLayout>
}
