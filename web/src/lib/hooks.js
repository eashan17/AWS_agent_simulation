import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// Templates and finished runs never change, so their answers are kept for the session.
const cache = new Map()
export function primeCache(key, value) { cache.set(key, value) }
export function dropCache(key) { cache.delete(key) }

/** useLoad(key, loader): {data, error, loading, reload}. key null = don't load. */
export function useLoad(key, loader, { keep = true } = {}) {
  const [state, setState] = useState(() =>
    key && cache.has(key) ? { data: cache.get(key), error: null, loading: false } : { data: null, error: null, loading: !!key })
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    if (!key) { setState({ data: null, error: null, loading: false }); return }
    if (keep && cache.has(key) && nonce === 0) { setState({ data: cache.get(key), error: null, loading: false }); return }
    let alive = true
    setState((s) => ({ data: s.data && s.key === key ? s.data : null, error: null, loading: true, key }))
    loaderRef.current()
      .then((data) => { if (!alive) return; if (keep) cache.set(key, data); setState({ data, error: null, loading: false, key }) })
      .catch((error) => { if (alive) setState({ data: null, error, loading: false, key }) })
    return () => { alive = false }
  }, [key, nonce, keep])

  const reload = useCallback(() => { if (key) cache.delete(key); setNonce((n) => n + 1) }, [key])
  return { ...state, reload }
}

export const useTemplates = () => useLoad('templates', api.templates)
export const useTemplate = (id) => useLoad(id ? `template:${id}` : null, () => api.template(id))
export const useBlueprint = (id) => useLoad(id ? `blueprint:${id}` : null, () => api.blueprint(id), { keep: false })
export const useFindings = (runId, status) =>
  useLoad(runId && status && status !== 'running' ? `findings:${runId}:${status}` : null, () => api.findings(runId))
/** How the AI people adapted (slice 19); read once the run has finished. */
export const useAdaptations = (runId, status) =>
  useLoad(runId && status && status !== 'running' ? `adapt:${runId}:${status}` : null, () => api.adaptations(runId))
export const useEvidence = (fid) => useLoad(fid ? `evidence:${fid}` : null, () => api.evidence(fid))
// Slice M3/M9: who carried the rule, per person, for a finished run.
export const useLedger = (runId, status) =>
  useLoad(runId && status && status !== 'running' ? `ledger:${runId}:${status}` : null, () => api.ledger(runId))
// Slice M7c: one person's decisions, each with the state it was made from (works while running too).
export const usePerson = (runId, person, status) =>
  useLoad(runId && person ? `person:${runId}:${person}:${status}` : null, () => api.person(runId, person), { keep: false })

export const templateIdOf = (ref) => (ref ? String(ref).split('@')[0] : null)

/**
 * useRun(runId): loads a run and, while it is `running`, polls `?after=<last seq>` every 3 s,
 * appending the new events. Stops polling when the run finishes. A network failure while
 * polling keeps the events so far and retries on the next tick.
 */
export function useRun(runId) {
  const [state, setState] = useState({ run: null, events: [], error: null, loading: !!runId, pollError: null })
  const lastSeq = useRef(0)

  useEffect(() => {
    if (!runId) return
    let alive = true
    let timer = null
    lastSeq.current = 0
    const key = `run:${runId}`
    if (cache.has(key)) {
      const r = cache.get(key)
      lastSeq.current = r.timeline.length ? r.timeline[r.timeline.length - 1].seq : 0
      setState({ run: r, events: r.timeline, error: null, loading: false, pollError: null })
      return
    }
    setState({ run: null, events: [], error: null, loading: true, pollError: null })

    const tick = async (first) => {
      try {
        const r = await api.run(runId, first ? 0 : lastSeq.current)
        if (!alive) return
        setState((s) => {
          const events = first ? r.timeline : [...s.events, ...r.timeline.filter((e) => e.seq > lastSeq.current)]
          if (events.length) lastSeq.current = events[events.length - 1].seq
          const run = { ...r, timeline: events }
          if (r.status !== 'running') cache.set(key, run)
          return { run, events, error: null, loading: false, pollError: null }
        })
        if (r.status === 'running') timer = setTimeout(() => tick(false), 3000)
      } catch (error) {
        if (!alive) return
        if (first) setState({ run: null, events: [], error, loading: false, pollError: null })
        else {
          setState((s) => ({ ...s, pollError: error }))
          timer = setTimeout(() => tick(false), 3000)
        }
      }
    }
    tick(true)
    return () => { alive = false; clearTimeout(timer) }
  }, [runId])

  return state
}

/** Seconds since `since` (a Date.now()), ticking each second while active. */
export function useElapsed(active) {
  const [start, setStart] = useState(null)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!active) { setStart(null); return }
    const s = Date.now()
    setStart(s); setNow(s)
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [active])
  return start ? Math.floor((now - start) / 1000) : 0
}

/** Server reachability for the sidebar pill: checks /api/health every 30 s. */
export function useHealth() {
  const [ok, setOk] = useState(null)
  useEffect(() => {
    let alive = true
    const check = () => api.health().then(() => alive && setOk(true)).catch(() => alive && setOk(false))
    check()
    const t = setInterval(check, 30000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  return ok
}
