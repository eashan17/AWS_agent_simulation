// What this browser is working on: the current run and blueprint, the policy draft and the
// what-if runs made from each run. Only IDs and the draft text; nothing secret.
import { useSyncExternalStore } from 'react'

const KEY = 'rulestorm.session.v1'

function load() {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* storage can be missing or blocked */ }
  return {}
}

let state = {
  runId: 'demo',
  blueprintId: null,
  draft: null,
  recent: ['demo'],
  whatIfs: {}, // source run id -> [what-if run ids], newest first
  searches: {}, // blueprint id -> its latest guided search id (slice 16b)
  ...load(),
}
const listeners = new Set()

function save() {
  try {
    const { runId, blueprintId, draft, recent, whatIfs, searches } = state
    window.localStorage.setItem(KEY, JSON.stringify({ runId, blueprintId, draft, recent, whatIfs, searches }))
  } catch { /* fine: it is a convenience */ }
}

export function setSession(patch) {
  state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) }
  save()
  listeners.forEach((l) => l())
}

export function useSession() {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l) },
    () => state,
  )
}

/** The run now open, and its blueprint, so the sidebar's Setup link follows the run. */
export function rememberRun(runId, blueprintId) {
  if (!runId) return
  setSession((s) => ({
    runId,
    ...(blueprintId ? { blueprintId } : {}),
    recent: [runId, ...(s.recent || []).filter((r) => r !== runId)].slice(0, 12),
  }))
}

export function rememberWhatIf(sourceId, newId) {
  setSession((s) => ({
    whatIfs: { ...s.whatIfs, [sourceId]: [newId, ...((s.whatIfs || {})[sourceId] || []).filter((r) => r !== newId)] },
    recent: [newId, ...(s.recent || []).filter((r) => r !== newId)].slice(0, 12),
  }))
}
