// A small hash router: no dependency, works when FastAPI serves index.html from any path.
import { useEffect, useState } from 'react'

function current() {
  const raw = window.location.hash.replace(/^#/, '') || '/'
  return raw.startsWith('/') ? raw : `/${raw}`
}

export function navigate(path) {
  if (current() === path) return
  window.location.hash = path
  window.scrollTo({ top: 0 })
}

export function useRoute() {
  const [path, setPath] = useState(current)
  useEffect(() => {
    const on = () => setPath(current())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return parse(path)
}

/** Routes: /  /setup  /blueprint/:id[/stress]  /run/:id  /run/:id/analysis[/:tab[/:arg]]  /runs */
export function parse(path) {
  const parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent)
  const [a, b, c, d, e] = parts
  if (!a) return { name: 'home', path }
  if (a === 'setup') return { name: 'setup', path }
  if (a === 'runs') return { name: 'runs', path }
  if (a === 'blueprint' && b) return { name: 'review', id: b, tab: c === 'stress' ? 'stress' : 'blueprint', path }
  if (a === 'run' && b && c === 'analysis') return { name: 'analysis', id: b, tab: d || 'summary', arg: e, path }
  if (a === 'run' && b) return { name: 'simulation', id: b, path }
  return { name: 'notfound', path }
}

export const href = (path) => `#${path}`
