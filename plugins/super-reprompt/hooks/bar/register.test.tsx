// Bout en bout, dans le moteur de Claude Code : vrais événements -> calcul -> barre dessinée.
import { expect, mock, test } from 'claude-code/testing'

const TOOL = 'mcp__super-reprompt__project'
const BAND = { plugin: 'super-reprompt', component: 'AbovePrompt', props: { hasSurvey: false, isWorking: true, maxRows: 12, bodyColumns: 99, scroll: { offset: 0, bodyRows: 12 }, view: {} } } as const
const MIN = 60_000
// Hors mission (pas de dossier .super-reprompt), le mod doit rester muet (invariant I7).
let MISSION = true
let REGISTERED: string[] = []
const LOGS: string[] = []

// Le monde sous le plugin : outils simulés, horloge et magasin en mémoire.
function world(on: any, store: Record<string, unknown> = {}, fails: (cmd: string) => string | undefined = () => undefined) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on, store)
  on('session.id', () => ({ value: 'session-test-1' }))
  on('tool.register', (_: any, e: any) => (REGISTERED.push(e.name), { value: { tool: `mcp__super-reprompt__${e.name}` } }))
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('turn.start', (_: any, e: any) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.log', (_: any, e: any) => (LOGS.push(JSON.stringify(e)), { value: undefined }))
  on('fs.stat', () => {
    if (!MISSION) throw new Error('ENOENT')
    return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
  })
  on('tool.call', (_: any, e: any) => {
    const bad = e.tool === 'Bash' ? fails(e.command) : undefined
    return bad === undefined ? { result: {}, text: e.tool === 'TaskCreate' ? `Task #${e.subject.length} created` : 'ok' } : { result: {}, text: bad, isError: true }
  })
  on('ui.render', ($: any, e: any) => { const { Text } = $.ui.resolve(e); return <Text>engine</Text> })
  return clock
}
const boot = ($: any) => $.session.start({ cwd: '/p', surface: 'desktop', isInteractive: true })
const call = async ($: any, input: any): Promise<string> => String((await $.tool.call({ tool: TOOL, ...input })).result)
const turn = ($: any, agentId?: string) => $.turn.start({ text: 'x', turnId: agentId ?? 't1', ...(agentId !== undefined && { agentId }) })
const end = ($: any, agentId?: string) => $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: agentId ?? 't1', reason: 'answer', ...(agentId !== undefined && { agentId }) })
async function seen($: any, surface: 'desktop' | 'terminal' = 'desktop'): Promise<{ bar: boolean; text: string }> {
  const ui = await $.ui.mount({ ...BAND, surface })
  const svg = surface === 'desktop' ? await ui.find({ type: 'Svg' }) : undefined
  const pct = await ui.find({ type: 'Text', text: /%/ })
  const eta = await ui.find({ type: 'Text', text: /◷/ })
  await ui.unmount()
  return { bar: svg !== undefined && svg !== null, text: `${pct?.text ?? ''}${eta?.text ?? ''}` }
}
const PLAN = { action: 'plan', title: 'Site', tasks: [
  { id: 'A', title: 'analyser', est_min: 4 },
  { id: 'B', title: 'coder', est_min: 12, verify: 'pytest' },
  { id: 'F', title: 'vérification finale', est_min: 2, final: true },
] }

test('hors projet : rien n’est dessiné', async ($, on) => {
  world(on)
  await boot($)
  await turn($)
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  const s = await seen($)
  expect(s.bar).toBe(false)
  expect(s.text).toBe('')
})

test('projet complet : la preuve vient des commandes réelles, 100 % à la fin seulement', async ($, on) => {
  let red = true
  const clock = world(on, {}, c => (c.includes('pytest') && red ? '2 failed' : undefined))
  await boot($)
  await turn($)
  await call($, PLAN)
  await call($, { action: 'update', start: ['A'] })
  expect((await seen($)).text).toContain('0 %')
  expect((await seen($)).text).toContain('estimation en cours')
  await clock.advance(4 * MIN)
  expect((await seen($)).text).toContain('0 %') // le temps seul n'avance rien
  await call($, { action: 'update', done: ['A'], start: ['B'] })
  expect((await seen($)).text).toContain('22 %')
  expect((await seen($)).text).toContain('≈')
  await clock.advance(5 * MIN)
  expect(await call($, { action: 'update', done: ['B'], evidence: 'promis' })).toContain('non comptée')
  await $.tool.call({ tool: 'Bash', command: 'pytest -q' })
  expect((await seen($)).text).toContain('22 %')
  red = false
  await call($, { action: 'update', done: ['B'] })
  await $.tool.call({ tool: 'Bash', command: 'pytest -q' })
  expect((await seen($)).text).toContain('88 %')
  expect((await seen($)).text).toContain('Finalisation en cours')
  await call($, { action: 'update', done: ['F'], evidence: 'relu' })
  expect((await seen($)).text).toContain('100 %')
  await end($)
  expect((await seen($)).text).toContain('terminé')
  await turn($)
  expect((await seen($)).bar).toBe(false) // terminé et vu : la barre se retire
})

test('découverte : le pourcentage baisse ; second plan : rien n’est remis à zéro', async ($, on) => {
  const clock = world(on)
  await boot($)
  await turn($)
  await call($, PLAN)
  await call($, { action: 'update', start: ['A'] })
  await clock.advance(4 * MIN)
  await call($, { action: 'update', done: ['A'] })
  await call($, { action: 'add', tasks: [{ title: 'migration', est_min: 18 }] })
  expect((await seen($)).text).toContain('11 %')
  expect(await call($, PLAN)).toContain('rien n’est remis à zéro')
  expect((await seen($)).text).toContain('11 %')
})

test('interruption : un autre chargement retrouve tout, l’absence n’est pas comptée', async ($, on) => {
  const clock = world(on)
  await boot($)
  await turn($)
  await call($, PLAN)
  await call($, { action: 'update', start: ['A'] })
  await clock.advance(4 * MIN)
  await call($, { action: 'update', done: ['A'], start: ['B'] })
  await end($)
  await clock.advance(30 * MIN)
  await boot($) // même événement qu'un rechargement ou une reprise
  const s = await call($, { action: 'status' })
  expect(s).toContain('22 %')
  expect((await seen($)).text).toContain('22 %')
  expect((await seen($)).text).toContain('≈')
})

test('liste native de l’app : suivie sans plan explicite, jamais remise à zéro', async ($, on) => {
  const clock = world(on)
  await boot($)
  await turn($)
  const plan = (input: any) => $.tool.call({ tool: 'mcp__ccd_turn__update_plan', ...input })
  await plan({ scope: 'first_task', items: ['Lire', 'Coder', 'Tester'].map((content, i) => ({ content, status: i === 0 ? 'in_progress' : 'pending' })) })
  await clock.advance(4 * MIN)
  await plan({ advance: true })
  const a = (await seen($)).text
  expect(a).not.toContain(' 0 %')
  await plan({ scope: 'continuation', items: [{ content: 'Coder', status: 'in_progress' }, { content: 'Tester', status: 'pending' }, { content: 'Publier', status: 'pending' }] })
  expect((await seen($)).text).not.toContain(' 0 %')
  await plan({ done: [1, 2, 3] })
  expect((await seen($)).text).not.toContain('100 %') // vérification finale encore due
  await $.tool.call({ tool: 'mcp__ccd_turn__wrap_up', recap: 'fini' })
  expect((await seen($)).text).toContain('100 %')
})

test('listes TodoWrite et TaskCreate', async ($, on) => {
  world(on)
  await boot($)
  await turn($)
  for (const subject of ['un', 'deux!', 'trois!!']) await $.tool.call({ tool: 'TaskCreate', subject, description: '' })
  expect((await seen($)).bar).toBe(true)
  await $.tool.call({ tool: 'TaskUpdate', taskId: '2', status: 'completed' })
  expect((await seen($)).text).not.toContain(' 0 %')
})

test('attente d’une réponse : temps non compté', async ($, on) => {
  const clock = world(on)
  await boot($)
  await turn($)
  await call($, PLAN)
  await call($, { action: 'update', start: ['A'] })
  await clock.advance(2 * MIN)
  await end($)
  await clock.advance(60 * MIN)
  await turn($)
  await clock.advance(2 * MIN)
  await call($, { action: 'update', done: ['A'], start: ['B'] })
  // 4 min réelles pour 4 estimées : B reste proche de 12 min, pas de 70.
  const m = /≈ (\d+) à (\d+) min/.exec((await seen($)).text)
  expect(Number(m?.[1])).toBeLessThan(16)
  expect(Number(m?.[2])).toBeLessThan(40)
})

test('entrées invalides : message clair, aucun dégât', async ($, on) => {
  world(on)
  await boot($)
  await turn($)
  expect(await call($, { action: 'update', done: ['A'] })).toContain('commencer par')
  expect(await call($, { action: 'plan' })).toContain('Refusé')
  await call($, PLAN)
  expect(await call($, { action: 'update', done: ['ZZ'], milestones: [{ task: 'A', title: 'absent' }] })).toContain('Tâche inconnue : ZZ')
  expect(await call($, { action: 'resume', project: 'nope' })).toContain('Projets de ce dossier')
})

test('terminal : même contenu en texte', async ($, on) => {
  world(on)
  await boot($)
  await turn($)
  await call($, PLAN)
  expect((await seen($, 'terminal')).text).toContain('0 %')
})

test('dessin : trois éléments, une ligne, gris neutres, aucune mention interdite', async ($, on) => {
  world(on)
  await boot($)
  await turn($)
  await call($, PLAN)
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  const svg: any = await ui.find({ type: 'Svg' })
  const src = String(svg?.props?.source ?? '')
  expect(src).toContain('height="3"')
  expect(svg?.props?.height).toBe(20)
  expect(svg?.props?.width).toBeLessThan(361)
  for (const bad of ['Analyse', 'Claude', 'animate', 'Gradient', '<text', '<circle']) expect(src.includes(bad)).toBe(false)
  const colors = [...src.matchAll(/#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/g)]
  expect(colors.length).toBeGreaterThan(0)
  for (const c of colors) expect(c[1] === c[2] && c[2] === c[3]).toBe(true)
  await ui.unmount()
})

test('hors mission : ni outil, ni consigne, ni barre, même avec une liste native de 3 étapes (I7)', async ($, on) => {
  MISSION = false
  REGISTERED = []
  world(on)
  try {
    await boot($)
    await turn($)
    await $.tool.call({ tool: 'mcp__ccd_turn__update_plan', scope: 'first_task', items: ['a', 'b', 'c'].map(content => ({ content, status: 'pending' })) })
    expect(REGISTERED.length).toBe(0)
    const s = await seen($)
    expect(s.bar).toBe(false)
    expect(s.text).toBe('')
  } finally { MISSION = true }
})

test('V3.1 lot 9 : avec une mission compilée, la barre affiche la projection BAR.json (PLAN + événements), sans liste séparée', async ($, on) => {
  world(on)
  LOGS.length = 0
  const BAR = JSON.stringify({ updated: '2026-11-25T10:00:00Z', display: { percent: 40, text: '20 min - 45 min (confiance faible)' } })
  on('fs.list', () => ({ value: [{ name: 'page-tarifs', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }))
  on('fs.exists', () => ({ value: true }))
  on('fs.read', () => ({ value: BAR }))
  await boot($)
  await turn($)
  await $.tool.call({ tool: 'Bash', command: 'py -3 scripts/manager.py done T1 --report r.txt --project . --slug page-tarifs' })
  const s = await seen($)
  expect(LOGS.join(' | ')).toBe('')
  expect(s.bar).toBe(true)
  expect(s.text).toContain('40 %')
  expect(s.text).toContain('20 min - 45 min')
})
