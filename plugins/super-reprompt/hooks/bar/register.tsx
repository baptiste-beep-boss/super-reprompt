// Branchement sur Claude Code : événements réels -> moteur -> valeur affichée. Aucun calcul, aucun style ici.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'
import * as E from './engine'
import * as S from './signals'
import { drawBar } from './bar'
import type { BarView } from '../types'

const TOOL = 'mcp__super-reprompt__project'
const bar = atom({ plugin: 'super-reprompt', key: 'bar' } as const, null)

const GUIDE = `# Suivi de projet
For any request that needs several steps (code, documents, research, anything over about 5 minutes), call ${TOOL} with action "plan" before the work starts: every task of the WHOLE request, adapted to it, each with est_min (active minutes) and, when a command can prove it, verify (a distinctive fragment of that command); deps for order; milestones for long tasks; the last task is the final verification. Then, as you work: "start" when a task begins, "done" only once it is verified, "milestone", "block", and "add" as soon as you discover work. Several starts and dones go in one call. The person's progress bar is computed from these calls and from the real results of commands; never mark a task done to move it. Skip it for questions and one-step edits. A later request that continues the same project uses "add", not a new "plan".`

const SCHEMA = {
  type: 'object',
  properties: {
    action: { type: 'string', enum: ['plan', 'add', 'update', 'status', 'resume'] },
    title: { type: 'string', description: 'plan: name of the project' },
    tasks: {
      type: 'array',
      description: 'plan, add: the tasks',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          kind: { type: 'string', enum: ['analyse', 'conception', 'code', 'integration', 'test', 'correction', 'verification', 'document', 'autre'] },
          est_min: { type: 'number', description: 'honest estimate, minutes of active work' },
          weight: { type: 'number', description: 'workload; default from est_min' },
          deps: { type: 'array', items: { type: 'string' } },
          milestones: { type: 'array', items: { type: 'string' } },
          verify: { type: 'string', description: 'fragment of the command whose success proves the task' },
          final: { type: 'boolean' },
        },
        required: ['title'],
      },
    },
    start: { type: 'array', items: { type: 'string' }, description: 'update: ids begun' },
    done: { type: 'array', items: { type: 'string' }, description: 'update: ids finished and verified' },
    evidence: { type: 'string', description: 'update: what proves the done ones when no command can' },
    milestones: { type: 'array', items: { type: 'object', properties: { task: { type: 'string' }, title: { type: 'string' } }, required: ['task', 'title'] } },
    block: { type: 'array', items: { type: 'string' } },
    drop: { type: 'array', items: { type: 'string' }, description: 'update: ids no longer part of the project' },
    project: { type: 'string', description: 'resume: id of an earlier project of this folder' },
  },
  required: ['action'],
}

type Args = {
  action: string; title?: string; tasks?: E.TaskInput[]; start?: string[]; done?: string[]; evidence?: string
  milestones?: { task: string; title: string }[]; block?: string[]; drop?: string[]; project?: string
}
type Saved = { project: E.Project; list: E.ListItem[]; explicit: boolean; numbers: Record<string, string> }

// État du module, reconstruit depuis $.store à chaque chargement : un rechargement ne perd rien.
let project: E.Project | null = null
let list: E.ListItem[] = []
let explicit = false
let numbers: Record<string, string> = {}
let hidden = false
let sessionId = ''
let cwd = ''
let saves: Promise<unknown> = Promise.resolve()
let ticking = false
// I7 : hors mission (pas de dossier .super-reprompt dans le dossier de travail), le mod ne fait rien :
// ni outil, ni consigne, ni barre, ni minuterie. Décidé une fois par session, au démarrage.
let active = false

async function missionActive($: EngineInterface, dir: string): Promise<boolean> {
  try {
    return (await $.fs.stat(`${dir}/.super-reprompt`)).kind === 'dir'
  } catch {
    return false
  }
}

const key = () => `session:${sessionId}`
const asArray = <T,>(x: T[] | undefined): T[] => (Array.isArray(x) ? x : [])

async function save($: EngineInterface) {
  if (project === null || sessionId === '') return
  const value: Saved = { project, list, explicit, numbers }
  const p = project
  // Une écriture à la fois : deux événements simultanés ne s'écrasent pas.
  saves = saves.then(async () => {
    await $.store.set(key(), value)
    const index = ((await $.store.get('index')) ?? []) as { id: string; cwd: string; title: string; at: number; key: string }[]
    const rest = index.filter(x => x.id !== p.id)
    const at = p.lastTick
    const next = [{ id: p.id, cwd, title: p.title, at, key: key() }, ...rest].slice(0, 40)
    for (const old of rest.slice(39)) if (old.key !== key()) await $.store.delete(old.key)
    await $.store.set('index', next)
  }).catch(x => $.ui.log(`super-reprompt: sauvegarde impossible (${String(x)})`))
  await saves
}

// V3.1 lot 9 : quand une mission compilée existe, la barre est la PROJECTION de PLAN.json + events.ndjson que
// scripts/progress.py écrit dans .super-reprompt/<mission>/BAR.json (manager next / done). Aucune liste séparée,
// aucun calcul ici : la plus récente est lue telle quelle. Sans BAR.json, le moteur ci-dessous reste le repli.
let planView: BarView | null = null

async function readPlanBar($: EngineInterface): Promise<BarView | null> {
  try {
    const base = `${cwd}/.super-reprompt`
    let best: { at: string; v: BarView } | null = null
    for (const d of await $.fs.list(base)) {
      if (d.kind !== 'dir') continue
      const p = `${base}/${d.name}/BAR.json`
      if (!(await $.fs.exists(p))) continue
      const b = JSON.parse(String(await $.fs.read(p))) as { updated?: string; display?: BarView }
      if (b.display === undefined || typeof b.display.percent !== 'number') continue
      const at = b.updated ?? ''
      if (best === null || at > best.at) best = { at, v: { percent: b.display.percent, text: String(b.display.text ?? '') } }
    }
    return best === null ? null : best.v
  } catch (x) {
    $.ui.log(`super-reprompt: projection BAR.json illisible (${String(x)})`)
    return null
  }
}

async function show($: EngineInterface) {
  const now = await $.clock.now()
  let v: BarView | null = planView
  if (v === null && project !== null && project.tasks.length > 0 && !hidden) {
    const w = E.view(project, now)
    v = { percent: w.percent, text: E.fmtEta(w.eta) }
  }
  const held = (await read($, bar)) as BarView | null
  // Redessiner seulement si une valeur affichée change.
  if (held?.percent !== v?.percent || held?.text !== v?.text) await update($, bar, () => v)
}

async function commit($: EngineInterface) {
  const p = project
  if (p !== null && E.isOver(p) && p.samples.length > 0) {
    // Projet fini : ses durées réelles étalonnent les suivants.
    const past = ((await $.store.get('history')) ?? []) as E.Sample[]
    await $.store.set('history', [...past, ...p.samples].slice(-200))
    project = { ...p, history: [...p.history, ...p.samples].slice(-200), samples: [] }
  }
  await save($)
  await show($)
}

async function begin($: EngineInterface, title: string, inputs: E.TaskInput[], now: number, source: E.Source) {
  const past = ((await $.store.get('history')) ?? []) as E.Sample[]
  const running = project?.running ?? {}
  const loops = Object.keys(running).length > 0 ? running : { main: now }
  project = { ...E.createProject(`${sessionId.slice(0, 8)}-${now.toString(36)}`, title, inputs, now, past, source), running: loops }
  hidden = false
}

function report(now: number, notes: string[] = []): string {
  if (project === null) return 'Aucun projet suivi.'
  const w = E.view(project, now)
  const open = project.tasks.filter(t => t.status !== 'done' && t.status !== 'dropped')
  return [
    `${w.percent} % · ${w.done}/${w.total} tâches · ${E.fmtEta(w.eta)}`,
    ...notes,
    ...(open.length > 0 ? [`Ouvertes : ${open.slice(0, 12).map(t => `${t.id}${t.status === 'doing' ? '*' : ''}`).join(', ')}`] : []),
  ].join('\n')
}

async function runTool($: EngineInterface, a: Args): Promise<string> {
  const now = await $.clock.now()
  const tasks = asArray(a.tasks).filter(t => typeof t?.title === 'string' && t.title.trim() !== '')
  const notes: string[] = []
  if (a.action === 'plan') {
    if (tasks.length === 0) return 'Refusé : un plan demande au moins une tâche.'
    if (project !== null && explicit && !E.isOver(project)) {
      project = E.addTasks(project, tasks, now)
      notes.push('Projet déjà en cours : tâches nouvelles ajoutées, rien n’est remis à zéro.')
    } else {
      await begin($, a.title ?? 'Projet', tasks, now, 'plan')
      explicit = true
    }
  } else if (a.action === 'resume') {
    const index = ((await $.store.get('index')) ?? []) as { id: string; cwd: string; title: string; key: string }[]
    const here = index.filter(x => x.cwd === cwd)
    const hit = here.find(x => x.id === a.project) ?? (a.project === undefined && here.length === 1 ? here[0] : undefined)
    const raw = hit === undefined ? undefined : ((await $.store.get(hit.key)) as Saved | undefined)
    const p = E.resume(raw?.project, now)
    if (p === null || hit === undefined || p.id !== hit.id) return `Projets de ce dossier : ${here.map(x => `${x.id} (${x.title})`).join(' ; ') || 'aucun'}`
    project = { ...p, waiting: false, running: { main: now } }
    explicit = true
    list = []
    hidden = false
  } else if (project === null) {
    return 'Aucun projet suivi : commencer par l’action plan.'
  } else if (a.action === 'add') {
    project = E.addTasks(project, tasks, now)
    hidden = false
  }
  if (project !== null && (a.action === 'update' || a.action === 'add')) {
    const each = (refs: string[] | undefined, f: (id: string) => void) => {
      for (const ref of asArray(refs)) {
        const t = E.find(project!, ref)
        if (t === undefined) notes.push(`Tâche inconnue : ${ref}`)
        else f(t.id)
      }
    }
    for (const m of asArray(a.milestones)) each([m.task], id => { project = E.reachMilestone(project!, id, m.title, now) })
    each(a.done, id => {
      const r = E.completeTask(project!, id, a.evidence, now)
      project = r.p
      if (!r.ok) notes.push(`${id} non comptée : ${r.why}`)
    })
    each(a.start, id => { project = E.startTask(project!, id, now) })
    each(a.block, id => { project = E.blockTask(project!, id, now) })
    each(a.drop, id => {
      project = E.dropTask(project!, id, now)
      if (E.find(project, id)?.status !== 'dropped') notes.push(`${id} gardée : déjà terminée, ou vérification finale (la clore avec done)`)
    })
  }
  await commit($)
  return report(now, notes)
}

// Listes natives : filet de sécurité quand aucun plan explicite n'a été posé.
async function nativeList($: EngineInterface, items: E.ListItem[], isNew: boolean) {
  list = items
  if (explicit && project !== null && !E.isOver(project)) return
  const now = await $.clock.now()
  if (project === null || isNew || (E.isOver(project) && items.some(i => i.status !== 'completed'))) {
    if (items.length < 3) return
    explicit = false
    await begin($, 'Projet', [], now, 'list')
  }
  project = E.syncList(project!, items, now)
  await commit($)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    cwd = e.cwd
    active = await missionActive($, cwd)
    if (!active) return next(e)
    sessionId = await $.session.id()
    const raw = (await $.store.get(key())) as Saved | undefined
    const now = await $.clock.now()
    project = E.resume(raw?.project, now)
    list = raw?.list ?? []
    explicit = raw?.explicit ?? false
    numbers = raw?.numbers ?? {}
    hidden = project !== null && E.isOver(project)
    await $.tool.register({ name: 'project', description: 'Declares and updates the project plan behind the person\'s progress bar (percent and time left for the WHOLE project).', inputSchema: SCHEMA, isDeferred: true })
    planView = await readPlanBar($)
    await show($)
    // Toutes les 5 s, l'horloge de travail avance ; rien n'est redessiné sans changement. La projection du plan, elle, ne
    // change qu'après une commande (manager next / done) : elle est relue après chaque Bash/PowerShell et en fin de tour.
    if (ticking) return next(e)
    ticking = true
    $.clock.every(5000, async () => {
      if (planView !== null) return
      if (project === null || hidden) return
      project = E.tick(project, await $.clock.now())
      await show($)
    })
    return next(e)
  })

  on('prompt.compose', async ($, e, next) => {
    const r = await next(e)
    if (!active || !e.tools.includes(TOOL)) return r
    return { sections: [...r.sections, { id: 'super-reprompt:guide', text: GUIDE, scope: 'session' as const }] }
  })

  on('turn.start', async ($, e, next) => {
    if (!active) return next(e)
    if (project !== null) {
      if (e.agentId === undefined && E.isOver(project)) hidden = true // terminé et vu : la barre se retire
      project = E.turnStart(project, e.agentId ?? 'main', await $.clock.now())
      await commit($)
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (!active) return next(e)
    if (project !== null) {
      project = E.turnEnd(project, e.agentId ?? 'main', await $.clock.now())
      await commit($)
    }
    const pv = await readPlanBar($)
    if (pv !== null || planView !== null) {
      planView = pv
      await show($)
    }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (!active) return next(e)
    const tool: string = e.tool
    // Servi ici et non par tool.run, absent des versions 2.1.310 et antérieures.
    if (tool === TOOL) return { result: await runTool($, e as unknown as Args) }
    if (tool === 'AskUserQuestion' && project !== null) {
      project = E.askUser(project, true, await $.clock.now())
      const r = await next(e)
      if (project !== null) project = E.askUser(project, false, await $.clock.now())
      await commit($)
      return r
    }
    const r = await next(e)
    const a = e as unknown as Record<string, unknown>
    const failed = r.deny !== undefined || r.isError === true
    if (tool === 'Bash' || tool === 'PowerShell') {
      const pv = await readPlanBar($)
      if (pv !== null || planView !== null) {
        planView = pv
        await show($)
      }
    }
    if ((tool === 'Bash' || tool === 'PowerShell') && project !== null && r.deny === undefined && a.run_in_background !== true) {
      const cmd = String(a.command ?? '')
      const v = S.verdict(cmd, failed, r.text ?? '')
      if (v !== 'unknown') {
        project = E.command(project, cmd, v === 'ok', await $.clock.now())
        await commit($)
      }
    } else if (!failed && project !== null && (tool === 'Edit' || tool === 'Write' || tool === 'NotebookEdit')) {
      project = E.edited(project, String(a.file_path ?? a.notebook_path ?? ''), await $.clock.now())
    } else if (!failed && tool === 'mcp__ccd_turn__update_plan') {
      const call = a as unknown as S.PlanCall
      await nativeList($, S.reduceList(list, call), call.scope === 'new_task')
    } else if (!failed && tool === 'TodoWrite') {
      await nativeList($, asArray(a.todos as E.ListItem[]), false)
    } else if (!failed && tool === 'TaskCreate') {
      const n = S.taskNumber(r.text ?? '')
      if (n !== undefined) numbers = { ...numbers, [n]: String(a.subject) }
      await nativeList($, [...list, { content: String(a.subject), status: 'pending' }], false)
    } else if (!failed && tool === 'TaskUpdate') {
      const title = numbers[String(a.taskId)]
      const status = a.status as string | undefined
      if (title !== undefined && status !== undefined)
        await nativeList($, status === 'deleted' ? list.filter(i => i.content !== title) : list.map(i => (i.content === title ? { ...i, status: status as E.ListItem['status'] } : i)), false)
    } else if (!failed && tool === 'mcp__ccd_turn__wrap_up' && project !== null && !explicit) {
      // Bilan de fin de tour : l'étape en cours est rendue ; ce qui reste à faire reste à faire.
      const now = await $.clock.now()
      list = list.map(i => (i.status === 'in_progress' ? { ...i, status: 'completed' } : i))
      project = E.syncList(project, list, now)
      const open = project.tasks.filter(t => t.status !== 'done' && t.status !== 'dropped')
      if (open.length === 1 && open[0]!.isFinal) project = E.completeTask(project, open[0]!.id, 'bilan de fin de tour', now).p
      await commit($)
    }
    return r
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const v = (await read($, bar)) as BarView | null
    if (!active || v === null || e.props.hasSurvey) return next(e)
    return drawBar($.ui.resolve(e), e.surface, e.props.bodyColumns, v)
  })
}
