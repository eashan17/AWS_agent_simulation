// Template → map layout. The map is a plain layout of places; there is no drawn route.
// Agents move straight (with a slight curve) between places, and their trails show the way.
// Zones come from the rules each role runs, never from template names:
//   recorder → the duty zone · queue_processor (or whoever decides requests) → the request desk ·
//   checker → the check gate. The most common AI role travels between home and the duty zone.
import { cap, humanize } from '../lib/words.js'

export const STAGE = { w: 1200, h: 620 }

function firstDuty(events) {
  for (const e of events || []) if (e.payload?.duty) return e.payload.duty
  return null
}

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]

export function buildLayout(words, events = []) {
  const travellers = words.travellers
  const n = travellers.length || 1
  const cols = n > 3 ? 2 : 1
  const rows = Math.ceil(n / cols)
  const houses = travellers.map((id, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const x = cols === 1 ? 150 : 80 + col * 160
    const y = rows === 1 ? 300 : rows === 2 ? 210 + row * 200 : 170 + (row * 280) / (rows - 1)
    return { id, x, y, spot: [x + 64, y + 24] }
  })
  const homeSpot = Object.fromEntries(houses.map((h) => [h.id, h.spot]))
  const index = Object.fromEntries(travellers.map((id, i) => [id, i]))

  // who sits where, from the rules each role runs (and, for AI deciders, from what they did)
  const deciders = new Set((events || []).filter((e) => ['queue_processed', 'request_decided', 'decision_awaiting', 'decision_not_made'].includes(e.type)).map((e) => e.actor))
  const posts = {}
  const zoneRoles = { duty: [], desk: [], check: [] }
  const commons = []
  for (const id of words.staff) {
    const rules = words.role(id)?.rules || []
    let zone = null
    if (rules.includes('recorder')) zone = 'duty'
    else if (rules.includes('queue_processor')) zone = 'desk'
    else if (rules.includes('checker')) zone = 'check'
    else if (deciders.has(id)) zone = 'desk'
    if (zone) zoneRoles[zone].push(id)
    else commons.push(id)
    posts[id] = zone || 'commons'
  }

  const duty = firstDuty(events)
  const zones = {
    duty: { x: 640, y: 250, w: 176, h: 128, label: duty ? cap(humanize(duty)) : cap(words.step), staff: zoneRoles.duty },
    desk: { x: 1040, y: 130, w: 212, h: 116, label: `${cap(words.terms.request)} desk`, staff: zoneRoles.desk },
    check: { x: 1040, y: 420, w: 200, h: 120, label: cap(words.template.checks?.[0]?.label || 'Check'), staff: zoneRoles.check },
    commons: { x: 640, y: 530, label: 'Support', staff: commons },
  }

  const staffSpot = {}
  const place = (ids, base, dx, dy = 0) => ids.forEach((id, i) => { staffSpot[id] = [base[0] + i * dx, base[1] + i * dy] })
  const ai = (ids) => ids.filter((id) => words.isAI(id))
  place(ai(zoneRoles.duty), [805, 300], 0, 56)
  place(ai(zoneRoles.desk), [868, 140], 0, 56)
  place(ai(zoneRoles.check), [880, 450], 0, 56)
  place(commons, [640 - ((commons.length - 1) * 56) / 2, 530], 56)

  const slot = (base, per, dx, dy) => (id) => {
    const i = index[id] ?? 0
    return [base[0] + (i % per) * dx, base[1] + Math.floor(i / per) * dy]
  }
  const dutySlot = slot([576, 398], 3, 64, 50)
  const hazard = [400, 280]

  return {
    travellers,
    houses,
    zones,
    posts,
    staffSpot,
    hazard,
    homeSpot: (id) => homeSpot[id] || [150, 300],
    dutySlot,
    // on the way: part-way from home to the duty zone
    onTheWay: (id) => lerp(homeSpot[id] || [150, 300], dutySlot(id), 0.6),
    // held up: gathered just short of the disruption
    heldUp: (id) => {
      const i = index[id] ?? 0
      return [hazard[0] - ((n - 1) * 30) / 2 + i * 30, hazard[1] - 78]
    },
    deskSlot: slot([975, 258], 3, 66, 46),
    checkSlot: slot([975, 528], 3, 66, 46),
  }
}

/** Where an agent stands for a zone. */
export function spotFor(layout, id, zone) {
  switch (zone) {
    case 'home': return { xy: layout.homeSpot(id) }
    case 'route': return { xy: layout.onTheWay(id) }
    case 'stuck': return { xy: layout.heldUp(id) }
    case 'duty': return { xy: layout.dutySlot(id) }
    case 'desk': return { xy: layout.deskSlot(id) }
    case 'check': return { xy: layout.checkSlot(id) }
    default: return { xy: layout.homeSpot(id) }
  }
}

/** A direct walk with a slight natural curve; alternate agents bend the other way. */
export function planPath(layout, id, from, to) {
  const [x0, y0] = from.xy
  const [x1, y1] = to.xy
  const d = Math.hypot(x1 - x0, y1 - y0)
  if (d < 1) return [[x1, y1]]
  const i = layout.travellers.indexOf(id)
  const bend = (i % 2 ? 1 : -1) * Math.min(60, d * 0.14)
  const nx = -(y1 - y0) / d
  const ny = (x1 - x0) / d
  const mx = (x0 + x1) / 2 + nx * bend
  const my = (y0 + y1) / 2 + ny * bend
  const pts = []
  const steps = Math.max(8, Math.round(d / 18))
  for (let k = 1; k <= steps; k++) {
    const t = k / steps
    const u = 1 - t
    pts.push([u * u * x0 + 2 * u * t * mx + t * t * x1, u * u * y0 + 2 * u * t * my + t * t * y1])
  }
  return pts
}
