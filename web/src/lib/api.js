// Same-origin calls to the RuleStorm API. Every failure becomes an ApiError with a real cause,
// so each screen can say what actually went wrong and what to do next.

export class ApiError extends Error {
  /**
   * kind: input (400/422) · notfound (404) · conflict (409) · limit (429) · server (5xx)
   *       · network (no answer) · timeout (we gave up waiting)
   */
  constructor(kind, { status = 0, detail = '', fields = {}, body = null } = {}) {
    super(detail || kind)
    this.kind = kind
    this.status = status
    this.detail = detail
    this.fields = fields
    this.body = body
  }
}

function kindFor(status) {
  if (status === 400 || status === 422) return 'input'
  if (status === 404) return 'notfound'
  if (status === 409) return 'conflict'
  if (status === 429) return 'limit'
  return 'server'
}

// FastAPI's 422 detail is a list of {loc, msg}; our own errors are a plain sentence.
function readDetail(body) {
  const fields = {}
  if (!body) return { detail: '', fields }
  const d = body.detail
  if (Array.isArray(d)) {
    const parts = d.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : ''
      const msg = String(item.msg || '').replace(/^Value error, /, '')
      if (field) fields[field] = msg
      return field ? `${field}: ${msg}` : msg
    })
    return { detail: parts.join('; '), fields }
  }
  return { detail: typeof d === 'string' ? d : '', fields }
}

export async function request(method, path, body, { timeoutMs = 20000, signal } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort('timeout'), timeoutMs)
  const onAbort = () => ctrl.abort('cancelled')
  signal?.addEventListener('abort', onAbort)
  let res
  try {
    res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
  } catch (err) {
    if (ctrl.signal.aborted && ctrl.signal.reason === 'timeout') throw new ApiError('timeout')
    if (ctrl.signal.aborted) throw new ApiError('cancelled')
    throw new ApiError('network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
  let data = null
  const text = await res.text()
  try { data = text ? JSON.parse(text) : null } catch { data = null }
  if (!res.ok) {
    // A proxy in front of a stopped server answers 502/503/504 with an HTML page.
    if (!data && res.status >= 500) throw new ApiError('network', { status: res.status })
    const { detail, fields } = readDetail(data)
    throw new ApiError(kindFor(res.status), { status: res.status, detail, fields, body: data })
  }
  return data
}

export const api = {
  health: () => request('GET', '/api/health', null, { timeoutMs: 6000 }),
  templates: () => request('GET', '/api/templates'),
  template: (id) => request('GET', `/api/templates/${encodeURIComponent(id)}`),
  blueprint: (id) => request('GET', `/api/blueprints/${encodeURIComponent(id)}`),
  savePolicy: (body) => request('POST', '/api/policies', body),
  buildBlueprint: (policyId) => request('POST', '/api/blueprints', { policy_id: policyId }, { timeoutMs: 65000 }),
  editValues: (id, changes) => request('PATCH', `/api/blueprints/${encodeURIComponent(id)}/values`, { changes }),
  approve: (id) => request('POST', `/api/blueprints/${encodeURIComponent(id)}/approve`),
  variants: (id) => request('POST', `/api/blueprints/${encodeURIComponent(id)}/variants`, null, { timeoutMs: 65000 }),
  startRun: (blueprintId) => request('POST', '/api/runs', { blueprint_id: blueprintId }),
  run: (id, after = 0) => request('GET', `/api/runs/${encodeURIComponent(id)}${after ? `?after=${after}` : ''}`),
  findings: (id) => request('GET', `/api/runs/${encodeURIComponent(id)}/findings`),
  evidence: (fid) => request('GET', `/api/findings/${encodeURIComponent(fid)}/evidence`),
  counterfactual: (id, parameter, value) =>
    request('POST', `/api/runs/${encodeURIComponent(id)}/counterfactual`, { parameter, value }),
  startSearch: (blueprintId, maxRuns) =>
    request('POST', `/api/blueprints/${encodeURIComponent(blueprintId)}/search`, { max_runs: maxRuns }),
  getSearch: (id) => request('GET', `/api/searches/${encodeURIComponent(id)}`),
  // the POST waits for the one AI call that writes the three versions
  startComparison: (blueprintId) => request('POST', '/api/comparisons', { blueprint_id: blueprintId }, { timeoutMs: 65000 }),
  getComparison: (id) => request('GET', `/api/comparisons/${encodeURIComponent(id)}`),
  compare: (a, b) => request('GET', `/api/runs/${encodeURIComponent(a)}/compare/${encodeURIComponent(b)}`),
}

/** One plain sentence for an error, in the words docs/USER_JOURNEY.md asks for. */
export function explain(err, context = {}) {
  if (!(err instanceof ApiError)) return 'Something went wrong in the page. Reload and try again.'
  switch (err.kind) {
    case 'network':
      return "The server didn't answer. Check your connection, then try again in a minute."
    case 'timeout':
      return context.timeout || 'The server took too long to answer. Try again.'
    case 'server':
      return "The server hit a problem and didn't finish. Try again in a minute."
    case 'limit':
      return context.limit ||
        "Today's limit for new simulations is reached. You can still open the demo run and any finished run."
    case 'notfound':
      return context.notfound || capitalise(err.detail) || 'Not found.'
    case 'conflict':
      if (err.body?.run_id) return 'Another simulation is running right now.'
      return capitalise(err.detail) || 'That clashes with the current state. Reload and try again.'
    case 'input':
      return capitalise(err.detail) || 'Check the values and try again.'
    default:
      return capitalise(err.detail) || 'Something went wrong.'
  }
}

export function capitalise(s) {
  if (!s) return ''
  return s.charAt(0).toUpperCase() + s.slice(1)
}
