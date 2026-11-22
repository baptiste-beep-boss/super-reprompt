// Moteur de progression d'un projet. Pur : ni Claude Code, ni horloge, ni affichage.
// Chaque fonction prend un état et rend un nouvel état ; le temps est toujours un argument (ms).

export type Status = 'todo' | 'doing' | 'done' | 'blocked' | 'dropped'
export type Kind = 'analyse' | 'conception' | 'code' | 'integration' | 'test' | 'correction' | 'verification' | 'document' | 'autre'
export type Milestone = { id: string; title: string; weight: number; done: boolean }
export type Source = 'plan' | 'list'
export type Task = {
  id: string
  title: string
  kind: Kind
  weight: number // charge, sans unité
  estMin: number // durée estimée à la création, en minutes de travail actif
  status: Status
  deps: string[]
  milestones: Milestone[]
  verify?: string // fragment de la commande dont la réussite prouve la tâche
  activeMs: number // temps actif attribué
  startedAt?: number
  doneAt?: number
  proof?: string
  claimed: boolean // déclarée finie, preuve attendue
  verifiedAt?: number // dernière réussite de la commande de preuve
  failures: number
  isFinal: boolean
  source: Source
}
export type Sample = { kind: Kind; est: number; act: number }
export type Project = {
  v: 2
  id: string
  title: string
  createdAt: number
  tasks: Task[]
  running: Record<string, number> // boucle -> début du tour : seul ce temps compte
  lastTick: number
  activeMs: number
  waiting: boolean // Claude a rendu la main
  samples: Sample[]
  history: Sample[] // projets précédents, figé au démarrage
  tests: { pass: number; fail: number; lastFailed: boolean }
  scopeChanges: number
  lastEditAt?: number // dernier fichier de code modifié
}
export type Confidence = 'faible' | 'moyenne' | 'bonne'
export type Eta =
  | { state: 'none' | 'estimating' | 'finalizing' | 'blocked' | 'done' }
  | { state: 'range'; lowMin: number; highMin: number; confidence: Confidence; waiting: boolean }
  | { state: 'point'; min: number; confidence: Confidence; waiting: boolean }
export type View = { percent: number; eta: Eta; title: string; done: number; total: number }
export type TaskInput = {
  id?: string
  title: string
  kind?: string
  weight?: number
  est_min?: number
  deps?: string[]
  milestones?: (string | { title: string; weight?: number })[]
  verify?: string
  final?: boolean
}

const KINDS: Kind[] = ['analyse', 'conception', 'code', 'integration', 'test', 'correction', 'verification', 'document', 'autre']
const DEFAULT_MIN: Record<Kind, number> = {
  analyse: 4, conception: 5, code: 8, integration: 6, test: 5, correction: 6, verification: 3, document: 5, autre: 5,
}
const GAP_MS = 600_000 // au-delà : veille ou coupure, non compté

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))
const isLive = (t: Task) => t.status !== 'dropped'
const sum = (xs: readonly number[]) => xs.reduce((s, x) => s + x, 0)

export const norm = (s: string) =>
  s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim()

export function kindOf(title: string, given?: string): Kind {
  const g = norm(given ?? '') as Kind
  if (KINDS.includes(g)) return g
  const t = norm(title)
  if (/\b(corrig|correct|fix|bug|repar|debug)/.test(t)) return 'correction'
  if (/\b(verif|valid|control|final|relire|relect|review)/.test(t)) return 'verification'
  if (/\b(test|essai|scenario)/.test(t)) return 'test'
  if (/\b(integr|connect|branch|deplo|install|charg)/.test(t)) return 'integration'
  if (/\b(analys|explor|lire|compren|etudi|audit|recherch|trouv)/.test(t)) return 'analyse'
  if (/\b(concev|concept|architect|planif|design|cadr)/.test(t)) return 'conception'
  if (/\b(document|redig|readme|note|rapport|cahier|vault)/.test(t)) return 'document'
  if (/\b(ecri|implement|developp|cree|constru|cod|ajout|refai)/.test(t)) return 'code'
  return 'autre'
}

// ------------------------------------------------------------------ plan

function makeTask(i: TaskInput, id: string, source: Source): Task {
  const kind = kindOf(i.title, i.kind)
  const hasWeight = i.weight !== undefined && i.weight > 0
  const hasEst = i.est_min !== undefined && i.est_min > 0
  const est = hasEst ? i.est_min! : hasWeight ? i.weight! * 3 : DEFAULT_MIN[kind]
  return {
    id,
    title: i.title.slice(0, 160),
    kind,
    weight: clamp(hasWeight ? i.weight! : est / 3, 0.1, 1000),
    estMin: clamp(est, 0.2, 6000),
    status: 'todo',
    deps: [...new Set(i.deps ?? [])],
    milestones: (i.milestones ?? []).map((m, k) => ({
      id: `${id}.${k + 1}`,
      title: typeof m === 'string' ? m : m.title,
      weight: typeof m !== 'string' && m.weight !== undefined && m.weight > 0 ? m.weight : 1,
      done: false,
    })),
    ...(i.verify !== undefined && norm(i.verify) !== '' && { verify: i.verify.trim() }),
    activeMs: 0,
    claimed: false,
    failures: 0,
    isFinal: i.final === true,
    source,
  }
}

function freshId(tasks: Task[], wanted?: string): string {
  const w = wanted?.trim()
  if (w && !tasks.some(t => t.id === w)) return w
  let n = tasks.length + 1
  while (tasks.some(t => t.id === `T${n}`)) n++
  return `T${n}`
}

// Une dernière tâche de vérification, toujours : sans elle, 100 % s'afficherait sans contrôle final.
function withFinal(tasks: Task[]): Task[] {
  if (tasks.some(t => t.isFinal && isLive(t))) return tasks
  const last = tasks.map(isLive).lastIndexOf(true)
  const lastTask = tasks[last]
  if (lastTask !== undefined && lastTask.kind === 'verification') return tasks.map((t, k) => (k === last ? { ...t, isFinal: true } : t))
  const total = sum(tasks.filter(isLive).map(t => t.weight))
  const input = { title: 'Vérification finale', kind: 'verification', weight: Math.max(0.3, total * 0.05), est_min: 2, final: true }
  return [...tasks, makeTask(input, freshId(tasks, 'FINAL'), 'plan')]
}

// Une dépendance circulaire rendrait le planning impossible : on coupe l'arête qui la ferme.
function breakCycles(tasks: Task[]): Task[] {
  const by = new Map(tasks.map(t => [t.id, t]))
  const state = new Map<string, 'open' | 'closed'>()
  const cut = new Set<string>()
  const visit = (id: string) => {
    state.set(id, 'open')
    for (const d of by.get(id)?.deps ?? []) {
      if (!by.has(d) || state.get(d) === 'open') cut.add(`${id}>${d}`)
      else if (!state.has(d)) visit(d)
    }
    state.set(id, 'closed')
  }
  for (const t of tasks) if (!state.has(t.id)) visit(t.id)
  return cut.size === 0 ? tasks : tasks.map(t => ({ ...t, deps: t.deps.filter(d => !cut.has(`${t.id}>${d}`)) }))
}

export function createProject(id: string, title: string, inputs: TaskInput[], now: number, history: Sample[] = [], source: Source = 'plan'): Project {
  let tasks: Task[] = []
  for (const i of inputs) tasks = [...tasks, makeTask(i, freshId(tasks, i.id), source)]
  return {
    v: 2,
    id,
    title: title.slice(0, 120),
    createdAt: now,
    tasks: tasks.length > 0 ? withFinal(breakCycles(tasks)) : [],
    running: {},
    lastTick: now,
    activeMs: 0,
    waiting: false,
    samples: [],
    history: history.slice(-200),
    tests: { pass: 0, fail: 0, lastFailed: false },
    scopeChanges: 0,
  }
}

export function addTasks(p: Project, inputs: TaskInput[], now: number, source: Source = 'plan'): Project {
  const q = tick(p, now)
  let tasks = q.tasks
  let added = 0
  for (const i of inputs) {
    if (tasks.some(t => isLive(t) && ((i.id !== undefined && t.id === i.id) || norm(t.title) === norm(i.title)))) continue
    const t = makeTask(i, freshId(tasks, i.id), source)
    if (t.isFinal) {
      tasks = [...tasks.map(x => (x.isFinal ? { ...x, isFinal: false } : x)), t]
      added++
      continue
    }
    const at = tasks.findIndex(x => x.isFinal && isLive(x))
    tasks = at >= 0 ? [...tasks.slice(0, at), t, ...tasks.slice(at)] : [...tasks, t]
    added++
  }
  if (added === 0) return q
  // Du travail neuf après la fin : la vérification finale est à refaire.
  tasks = tasks.map(t => (t.isFinal && t.status === 'done' ? { ...t, status: 'todo' as const, doneAt: undefined, proof: undefined, claimed: false } : t))
  return { ...q, tasks: withFinal(breakCycles(tasks)), scopeChanges: q.scopeChanges + added }
}

// ------------------------------------------------------------------ horloge de travail

// Le temps actif est partagé entre les tâches en cours, seulement pendant qu'un tour tourne.
export function tick(p: Project, now: number): Project {
  const dt = now - p.lastTick
  if (dt <= 0) return p
  const loops = Object.keys(p.running).length
  if (loops === 0 || p.waiting || dt > GAP_MS) return { ...p, lastTick: now }
  const doing = p.tasks.filter(t => t.status === 'doing').length
  const share = doing > 0 ? (dt * Math.min(loops, doing)) / doing : 0
  return {
    ...p,
    lastTick: now,
    activeMs: p.activeMs + dt,
    tasks: share > 0 ? p.tasks.map(t => (t.status === 'doing' ? { ...t, activeMs: t.activeMs + share } : t)) : p.tasks,
  }
}

export function turnStart(p: Project, loop: string, now: number): Project {
  const q = tick(p, now)
  return { ...q, waiting: false, running: { ...q.running, [loop]: now } }
}

export function turnEnd(p: Project, loop: string, now: number): Project {
  const q = tick(p, now)
  const running = Object.fromEntries(Object.entries(q.running).filter(([k]) => k !== loop))
  return { ...q, running, waiting: Object.keys(running).length === 0 }
}

export const askUser = (p: Project, asking: boolean, now: number): Project => ({ ...tick(p, now), waiting: asking })

// ------------------------------------------------------------------ vie des tâches

const patch = (p: Project, id: string, f: (t: Task) => Task): Project => ({ ...p, tasks: p.tasks.map(t => (t.id === id ? f(t) : t)) })

export const find = (p: Project, ref: string): Task | undefined =>
  p.tasks.find(t => t.id === ref) ?? p.tasks.find(t => isLive(t) && norm(t.title) === norm(ref))

const reopened = (t: Task, now: number): Task => ({ ...t, status: 'doing', startedAt: t.startedAt ?? now, claimed: false, doneAt: undefined, proof: undefined })

export function startTask(p: Project, id: string, now: number): Project {
  return patch(tick(p, now), id, t => (t.status === 'dropped' ? t : reopened(t, now)))
}

export function blockTask(p: Project, id: string, now: number): Project {
  return patch(tick(p, now), id, t => (t.status === 'done' ? t : { ...t, status: 'blocked' }))
}

export function dropTask(p: Project, id: string, now: number): Project {
  return patch(tick(p, now), id, t => (t.isFinal || t.status === 'done' ? t : { ...t, status: 'dropped' }))
}

export function reachMilestone(p: Project, id: string, title: string, now: number): Project {
  const same = (m: Milestone) => m.id === title || norm(m.title) === norm(title)
  return patch(tick(p, now), id, t => ({ ...t, milestones: t.milestones.map(m => (same(m) ? { ...m, done: true } : m)) }))
}

function finish(p: Project, id: string, proof: string, now: number): Project {
  const t = p.tasks.find(x => x.id === id)
  if (t === undefined || t.status === 'done' || t.status === 'dropped') return p
  const act = t.activeMs / 60_000
  // Moins de 3 s observées : durée non mesurée, elle n'étalonne rien.
  const samples = act >= 0.05 ? [...p.samples, { kind: t.kind, est: t.estMin, act }].slice(-300) : p.samples
  return patch({ ...p, samples }, id, x => ({ ...x, status: 'done', doneAt: now, proof, claimed: false, milestones: x.milestones.map(m => ({ ...m, done: true })) }))
}

export type Completion = { p: Project; ok: boolean; why?: string }

// Fin demandée. Sans la preuve exigée, la tâche reste « déclarée » et n'est pas comptée.
export function completeTask(p: Project, id: string, evidence: string | undefined, now: number): Completion {
  const q = tick(p, now)
  const t = q.tasks.find(x => x.id === id)
  if (t === undefined || t.status === 'dropped') return { p: q, ok: false, why: 'tâche inconnue ou abandonnée' }
  if (t.status === 'done') return { p: q, ok: true }
  const refuse = (why: string): Completion => ({ p: patch(q, id, x => ({ ...reopened(x, now), claimed: true })), ok: false, why })
  const proven = t.verifiedAt !== undefined && t.verifiedAt >= (q.lastEditAt ?? 0)
  if (t.verify !== undefined && proven) return { p: finish(q, id, `commande réussie : ${t.verify}`, now), ok: true }
  if (t.verify !== undefined) return refuse(`preuve attendue : une commande réussie contenant « ${t.verify} »`)
  if (t.isFinal) {
    const left = q.tasks.filter(x => isLive(x) && x.id !== id && x.status !== 'done').length
    if (left > 0) return refuse(`${left} tâche(s) non terminée(s)`)
  }
  const needsGreen = t.isFinal || t.kind === 'code' || t.kind === 'correction' || t.kind === 'test' || t.kind === 'integration'
  if (needsGreen && q.tests.lastFailed) return refuse('les derniers tests ont échoué')
  return { p: finish(q, id, evidence?.slice(0, 200) || 'déclarée, sans commande de preuve', now), ok: true }
}

const CHECK = /(^|[\s;&|"'/\\])(pytest|unittest|vitest|jest|mocha|tox|ctest|go test|cargo (test|check|clippy)|(npm|pnpm|yarn|bun)( run)? (test|lint|build|check)|node --test|claude plugin (test|validate)|tsc|ruff|eslint|mypy|dotnet test|mvn|gradle|phpunit|rspec)(\s|$|["';&|])/i
export const isCheck = (cmd: string) => CHECK.test(cmd)

// Résultat réel d'une commande : preuve, échec, cycle de correction, régression.
export function command(p: Project, cmd: string, ok: boolean, now: number): Project {
  let q = tick(p, now)
  const check = isCheck(cmd)
  const c = norm(cmd)
  const hit = (t: Task) => t.verify !== undefined && c.includes(norm(t.verify))
  if (check) q = { ...q, tests: { pass: q.tests.pass + (ok ? 1 : 0), fail: q.tests.fail + (ok ? 0 : 1), lastFailed: !ok } }
  if (!ok) {
    return { ...q, tasks: q.tasks.map(t => {
      if (hit(t) && t.status === 'done') return { ...reopened(t, now), verifiedAt: undefined, failures: t.failures + 1 } // régression
      if (t.status === 'doing' && (hit(t) || check)) return { ...t, verifiedAt: undefined, failures: t.failures + 1 }
      return t
    }) }
  }
  q = { ...q, tasks: q.tasks.map(t => (hit(t) ? { ...t, verifiedAt: now } : t)) }
  for (const t of q.tasks) if (hit(t) && t.claimed && t.status === 'doing') q = finish(q, t.id, `commande réussie : ${cmd.slice(0, 120)}`, now)
  return q
}

// Un fichier de code modifié périme les preuves obtenues avant ; un texte, non.
export function edited(p: Project, path: string, now: number): Project {
  const q = tick(p, now)
  return /\.(md|txt|rst|adoc)$/i.test(path) ? q : { ...q, lastEditAt: now }
}

// ------------------------------------------------------------------ pourcentage

export function taskFraction(t: Task): number {
  if (t.status === 'done') return 1
  const all = sum(t.milestones.map(m => m.weight))
  // Jamais 50 % par défaut : sans jalon atteint, une tâche en cours vaut 0.
  return all === 0 ? 0 : Math.min(0.95, sum(t.milestones.filter(m => m.done).map(m => m.weight)) / all)
}

export function percent(p: Project): number {
  const live = p.tasks.filter(isLive)
  const total = sum(live.map(t => t.weight))
  if (total === 0) return 0
  if (live.every(t => t.status === 'done')) return 100
  return Math.min(99, Math.floor((sum(live.map(t => t.weight * taskFraction(t))) / total) * 100 + 1e-9))
}

// ------------------------------------------------------------------ temps restant

// Correction des estimations : moyenne des log(réel / estimé), rétrécie vers le global, puis vers 1.
export function calibration(p: Project, kind: Kind): { mean: number; sd: number; n: number } {
  const row = (s: Sample, w: number) => ({ x: Math.log(clamp(s.act / s.est, 0.02, 50)), w, kind: s.kind })
  // L'historique compte quatre fois moins que le projet en cours.
  const all = [...p.samples.map(s => row(s, 1)), ...p.history.map(s => row(s, 0.25))]
  const shrink = (xs: typeof all, prior: number) => (prior * 2 + sum(xs.map(r => r.x * r.w))) / (2 + sum(xs.map(r => r.w)))
  const global = shrink(all, 0)
  const n = sum(all.map(r => r.w))
  const spread = n > 0 ? sum(all.map(r => r.w * (r.x - global) ** 2)) / n : 0
  return { mean: shrink(all.filter(r => r.kind === kind), global), sd: Math.sqrt((0.49 * 3 + spread * n) / (3 + n)), n }
}

// Minutes actives restantes d'une tâche.
export function remainingMin(p: Project, t: Task): number {
  if (t.status === 'done' || t.status === 'dropped') return 0
  const full = t.estMin * Math.exp(calibration(p, t.kind).mean) * (1 + 0.35 * Math.min(4, t.failures))
  const byMilestone = full * (1 - taskFraction(t))
  if (t.status !== 'doing') return byMilestone
  const spent = t.activeMs / 60_000
  // Dépassement : il reste au moins une part de ce que la tâche a déjà coûté.
  const left = Math.max(full - spent, spent * 0.2, full * 0.08)
  if (t.claimed) return Math.min(left, full * 0.25)
  return t.milestones.some(m => m.done) ? Math.max(Math.min(left, byMilestone), full * 0.05) : left
}

// Corrections probables : taux d'échec observé des contrôles, appliqué au code restant.
export function reworkMin(p: Project, rest: Map<string, number>): number {
  const rate = (p.tests.fail + 1) / (p.tests.pass + p.tests.fail + 5) // a priori 20 %
  const code = p.tasks.filter(t => t.kind === 'code' || t.kind === 'integration' || t.kind === 'correction')
  return sum(code.map(t => rest.get(t.id) ?? 0)) * rate * 0.5
}

// Durée du graphe restant sur `width` voies : ni simple somme, ni simple division.
export function schedule(p: Project, rest: Map<string, number>, width: number): number {
  const open = p.tasks.filter(t => isLive(t) && t.status !== 'done')
  const ids = new Set(open.map(t => t.id))
  const plain = open.filter(t => !t.isFinal).map(t => t.id)
  const deps = new Map(open.map(t => [t.id, (t.isFinal ? [...t.deps, ...plain] : t.deps).filter(d => ids.has(d) && d !== t.id)]))
  const next = new Map<string, string[]>()
  for (const [id, ds] of deps) for (const d of ds) next.set(d, [...(next.get(d) ?? []), id])
  const cost = (id: string) => rest.get(id) ?? 0
  // Rang : plus long chemin jusqu'à la fin, pour lancer d'abord le chemin critique.
  const rank = new Map<string, number>()
  const rankOf = (id: string): number => {
    const known = rank.get(id)
    if (known !== undefined) return known
    rank.set(id, cost(id))
    const r = cost(id) + Math.max(0, ...(next.get(id) ?? []).map(rankOf))
    rank.set(id, r)
    return r
  }
  const doing = new Set(open.filter(t => t.status === 'doing').map(t => t.id))
  const order = (a: string, b: string) => Number(doing.has(b)) - Number(doing.has(a)) || rankOf(b) - rankOf(a)
  const end = new Map<string, number>()
  const lanes = Array.from({ length: Math.max(1, width) }, () => 0)
  const todo = new Set(open.map(t => t.id))
  while (todo.size > 0) {
    const id = [...todo].filter(x => (deps.get(x) ?? []).every(d => end.has(d))).sort(order)[0]
    if (id === undefined) break
    const lane = lanes.indexOf(Math.min(...lanes))
    const at = Math.max(lanes[lane]!, ...(deps.get(id) ?? []).map(d => end.get(d) ?? 0)) + cost(id)
    lanes[lane] = at
    end.set(id, at)
    todo.delete(id)
  }
  return Math.max(0, ...end.values())
}

export function eta(p: Project, now: number): Eta {
  const live = p.tasks.filter(isLive)
  if (live.length === 0) return { state: 'none' }
  const open = live.filter(t => t.status !== 'done')
  if (open.length === 0) return { state: 'done' }
  if (open.every(t => t.isFinal)) return { state: 'finalizing' }
  if (open.every(t => t.status === 'blocked' || t.isFinal)) return { state: 'blocked' }
  const q = tick(p, now)
  const cal = calibration(q, 'autre')
  // Rien de mesuré : aucun chiffre avant une minute de travail réel.
  if (cal.n === 0 && q.activeMs < 60_000) return { state: 'estimating' }
  const rest = new Map(q.tasks.map(t => [t.id, remainingMin(q, t)]))
  // Parallélisme constaté maintenant, jamais supposé.
  const loops = Math.max(1, Object.keys(q.running).length)
  const width = Math.max(1, Math.min(loops, q.tasks.filter(t => t.status === 'doing').length))
  const mid = schedule(q, rest, width) + reworkMin(q, rest) / width
  const confidence: Confidence = cal.n >= 6 ? 'bonne' : cal.n >= 3 ? 'moyenne' : 'faible'
  if (confidence !== 'faible') return { state: 'point', min: mid, confidence, waiting: q.waiting }
  const spread = Math.max(0.15, cal.sd * (0.45 + 0.55 / Math.sqrt(open.length)))
  return { state: 'range', lowMin: mid * Math.exp(-0.84 * spread), highMin: mid * Math.exp(0.84 * spread), confidence, waiting: q.waiting }
}

const round = (m: number) => (m < 1 ? 1 : m < 20 ? Math.round(m) : m < 60 ? Math.round(m / 5) * 5 : Math.round(m / 15) * 15)

export function fmtMin(m: number): string {
  const r = round(m)
  if (r < 60) return `${r} min`
  const rest = r % 60
  return rest === 0 ? `${r / 60} h` : `${Math.floor(r / 60)} h ${String(rest).padStart(2, '0')}`
}

export function fmtEta(e: Eta): string {
  if (e.state === 'estimating') return 'estimation en cours'
  if (e.state === 'finalizing') return 'Finalisation en cours'
  if (e.state === 'blocked') return 'projet bloqué'
  if (e.state === 'done') return 'terminé'
  if (e.state === 'point') return `≈ ${fmtMin(e.min)} restante${round(e.min) > 1 ? 's' : ''}`
  if (e.state === 'range') {
    const a = fmtMin(e.lowMin)
    const b = fmtMin(e.highMin)
    if (a === b) return `≈ ${b} restante${round(e.highMin) > 1 ? 's' : ''}`
    return a.endsWith(' min') && b.endsWith(' min') ? `≈ ${a.slice(0, -4)} à ${b} restantes` : `≈ ${a} à ${b} restantes`
  }
  return ''
}

export function view(p: Project, now: number): View {
  const live = p.tasks.filter(isLive)
  return { percent: percent(p), eta: eta(p, now), title: p.title, done: live.filter(t => t.status === 'done').length, total: live.length }
}

// ------------------------------------------------------------------ listes de tâches natives (filet)

export type ListItem = { content: string; status: 'pending' | 'in_progress' | 'completed' }

// Une liste ré-émise est rapprochée par intitulé : jamais de remise à zéro.
export function syncList(p: Project, items: ListItem[], now: number): Project {
  const twin = (q: Project, i: ListItem) => q.tasks.find(t => isLive(t) && norm(t.title) === norm(i.content))
  let q = tick(p, now)
  const fresh = items.filter(i => twin(q, i) === undefined)
  if (fresh.length > 0) q = addTasks(q, fresh.map(i => ({ title: i.content })), now, 'list')
  for (const i of items) {
    const t = twin(q, i)
    if (t === undefined) continue
    if (i.status === 'completed' && t.status !== 'done') q = completeTask(q, t.id, 'cochée dans la liste de tâches', now).p
    if (i.status === 'in_progress' && t.status !== 'doing') q = startTask(q, t.id, now)
  }
  // Issue d'une liste, absente de la nouvelle et jamais commencée : abandonnée.
  for (const t of q.tasks)
    if (t.source === 'list' && t.status === 'todo' && !t.isFinal && !items.some(i => norm(i.content) === norm(t.title))) q = dropTask(q, t.id, now)
  return q
}

// Reprise après coupure : plus aucun tour ne tourne, rien d'autre ne change.
export function resume(raw: unknown, now: number): Project | null {
  const p = raw as Project | null
  if (p === null || typeof p !== 'object' || p.v !== 2 || !Array.isArray(p.tasks)) return null
  // Un état ancien a pu garder deux finales : elles se bloqueraient l’une l’autre.
  const last = p.tasks.map(t => t.isFinal && isLive(t)).lastIndexOf(true)
  const tasks = p.tasks.map((t, k) => (t.isFinal && k !== last ? { ...t, isFinal: false } : t))
  return { ...p, tasks, running: {}, waiting: true, lastTick: now }
}

export const isOver = (p: Project) => p.tasks.length > 0 && p.tasks.filter(isLive).every(t => t.status === 'done')
