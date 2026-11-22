// Les six scénarios demandés, plus les règles de calcul. Lancer : node --test tests/engine.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import * as E from '../../hooks/bar/engine.ts'

const MIN = 60_000
// Petit banc : un projet et une horloge simulée.
function bench(inputs, opts = {}) {
  const b = { now: 0, p: E.createProject('x', 'Projet', inputs, 0, opts.history ?? []) }
  b.go = min => { for (let i = 0; i < min * 4; i++) { b.now += MIN / 4; b.p = E.tick(b.p, b.now) } }
  b.on = (loop = 'main') => { b.p = E.turnStart(b.p, loop, b.now) }
  b.off = (loop = 'main') => { b.p = E.turnEnd(b.p, loop, b.now) }
  b.start = id => { b.p = E.startTask(b.p, id, b.now) }
  b.done = (id, ev = 'fichier relu') => { const r = E.completeTask(b.p, id, ev, b.now); b.p = r.p; return r }
  b.cmd = (c, ok) => { b.p = E.command(b.p, c, ok, b.now) }
  b.pct = () => E.percent(b.p)
  b.eta = () => E.eta(b.p, b.now)
  b.mid = () => { const e = b.eta(); return e.state === 'point' ? e.min : Math.sqrt(e.lowMin * e.highMin) }
  b.txt = () => E.fmtEta(b.eta())
  return b
}

test('règles : pondération, jamais 50 % arbitraire, jamais de progression avec le temps', () => {
  const b = bench([{ id: 'A', title: 'simple', weight: 1 }, { id: 'B', title: 'complexe', weight: 9 }, { id: 'F', title: 'vérification finale', weight: 1, final: true }])
  assert.equal(b.pct(), 0)
  b.on(); b.start('B')
  assert.equal(b.pct(), 0, 'en cours ne vaut pas 50 %')
  b.go(30)
  assert.equal(b.pct(), 0, 'le temps seul ne fait pas avancer')
  b.done('A')
  assert.equal(b.pct(), 9) // 1/11
  b.done('B')
  assert.equal(b.pct(), 90)
  b.done('F')
  assert.equal(b.pct(), 100)
  assert.equal(b.txt(), 'terminé')
})

test('règles : preuve exigée, une tâche déclarée ne compte pas', () => {
  const b = bench([{ id: 'A', title: 'écrire le moteur', weight: 4, verify: 'node --test' }, { id: 'F', title: 'vérification finale', weight: 1, final: true }])
  b.on(); b.start('A'); b.go(3)
  const r = b.done('A', 'je jure que ça marche')
  assert.equal(r.ok, false); assert.equal(b.pct(), 0)
  b.cmd('node --test tests/', false); assert.equal(b.pct(), 0)
  b.done('A'); b.cmd('node --test tests/', true)
  assert.equal(b.pct(), 80)
  assert.match(b.p.tasks[0].proof, /commande réussie/)
  b.cmd('node --test tests/', false)
  assert.equal(b.pct(), 0, 'une régression rouvre la tâche')
})

test('règles : 100 % interdit avant la vérification finale, ajoutée si absente', () => {
  const b = bench([{ id: 'A', title: 'a', weight: 100 }])
  assert.equal(b.p.tasks.at(-1).isFinal, true)
  assert.equal(b.done(b.p.tasks.at(-1).id).ok, false, 'finale refusée tant que le reste est ouvert')
  b.on(); b.start('A'); b.done('A')
  assert.ok(b.pct() < 100); assert.equal(b.txt(), 'Finalisation en cours')
  b.cmd('pytest', false)
  assert.equal(b.done('FINAL').ok, false, 'finale refusée si les tests échouent')
  b.cmd('pytest', true); b.done('FINAL')
  assert.equal(b.pct(), 100)
})

test('règles : jalons pondérés', () => {
  const b = bench([{ id: 'A', title: 'a', weight: 8, milestones: ['un', { title: 'deux', weight: 3 }] }, { id: 'F', title: 'fin', weight: 2, final: true }])
  b.on(); b.start('A')
  b.p = E.reachMilestone(b.p, 'A', 'un', b.now)
  assert.equal(b.pct(), 20) // 8 * 1/4 / 10
  b.p = E.reachMilestone(b.p, 'A', 'DEUX', b.now)
  assert.equal(b.pct(), 76, 'tous les jalons ne valent pas la fin vérifiée (95 % au plus)')
})

test('1. projet simple : estimation honnête puis chiffrée', () => {
  const b = bench([{ id: 'A', title: 'lire', est_min: 4 }, { id: 'B', title: 'coder', est_min: 8 }, { id: 'F', title: 'vérification finale', est_min: 2, final: true }])
  b.on(); b.start('A')
  assert.equal(b.txt(), 'estimation en cours')
  b.go(4); b.done('A'); b.start('B')
  const e = b.eta()
  assert.equal(e.state, 'range'); assert.equal(e.confidence, 'faible')
  assert.ok(e.lowMin < 10 && e.highMin > 10, `${e.lowMin}..${e.highMin}`)
  const before = b.mid(); b.go(4)
  assert.ok(b.mid() < before, 'le temps restant baisse quand le travail avance')
  b.go(4); b.done('B'); assert.equal(b.txt(), 'Finalisation en cours')
})

test('2. projet complexe, 40 tâches deux fois plus lentes que prévu : le moteur apprend', () => {
  const inputs = Array.from({ length: 40 }, (_, i) => ({ id: `t${i}`, title: `coder ${i}`, est_min: 2 + (i % 4), deps: i > 0 ? [`t${i - 1}`] : [] }))
  const b = bench(inputs)
  b.on()
  let last = -1
  for (let i = 0; i < 30; i++) {
    b.start(`t${i}`); b.go((2 + (i % 4)) * 2); b.done(`t${i}`)
    assert.ok(b.pct() >= last); last = b.pct()
  }
  const truth = inputs.slice(30).reduce((s, t) => s + t.est_min * 2, 0) + 2 * 2
  const e = b.eta()
  assert.equal(e.state, 'point'); assert.equal(e.confidence, 'bonne')
  assert.ok(Math.abs(e.min - truth) / truth < 0.25, `estimé ${e.min.toFixed(1)}, vrai ${truth}`)
  // 103 minutes estimées finies sur 140, plus 5 % de vérification finale : 103 / 147
  assert.equal(b.pct(), 70)
})

test('3. tâches découvertes : le pourcentage baisse, le temps monte, rien n\'est perdu', () => {
  const b = bench([{ id: 'A', title: 'a', est_min: 6 }, { id: 'B', title: 'b', est_min: 6 }, { id: 'F', title: 'fin', est_min: 1, final: true }])
  b.on(); b.start('A'); b.go(6); b.done('A'); b.start('B')
  const pct = b.pct(), t = b.mid()
  b.p = E.addTasks(b.p, [{ title: 'migration imprévue', est_min: 12 }, { title: 'a', est_min: 99 }], b.now)
  assert.ok(b.pct() < pct); assert.ok(b.mid() > t)
  assert.equal(b.p.tasks.length, 4, 'un doublon n\'est pas ajouté')
  assert.equal(b.p.scopeChanges, 1)
  assert.equal(E.find(b.p, 'A').status, 'done')
  assert.equal(b.p.tasks.at(-1).isFinal, true, 'la finale reste dernière')
  b.go(6); b.done('B'); b.start('migration imprévue'); const m = E.find(b.p, 'migration imprévue'); b.start(m.id); b.go(12); b.done(m.id); b.done('F')
  assert.equal(b.pct(), 100)
  b.p = E.addTasks(b.p, [{ title: 'oubli' }], b.now)
  assert.ok(b.pct() < 100); assert.equal(E.find(b.p, 'F').status, 'todo', 'la finale est à refaire')
})

test('4. erreurs et corrections : le temps restant intègre les échecs, la tâche reste ouverte', () => {
  const mk = () => bench([{ id: 'A', title: 'coder', est_min: 10, verify: 'pytest' }, { id: 'B', title: 'coder la suite', est_min: 20 }, { id: 'F', title: 'fin', est_min: 1, final: true }])
  const ok = mk(), ko = mk()
  for (const b of [ok, ko]) { b.on(); b.start('A'); b.go(5) }
  for (let i = 0; i < 4; i++) { ko.cmd('pytest -q', false); ok.cmd('pytest -q', true) }
  assert.ok(ko.mid() > ok.mid() * 1.15, `${ko.mid()} contre ${ok.mid()}`)
  assert.equal(E.find(ko.p, 'A').failures, 4); assert.equal(ko.pct(), 0)
  assert.equal(ko.done('A').ok, false)
  ko.cmd('pytest -q', true)
  assert.equal(E.find(ko.p, 'A').status, 'done')
  ko.start('A'); ko.done('A'); ko.cmd('pytest -q', false)
  assert.equal(ko.done('B').ok, false, 'code refusé quand les derniers tests échouent')
})

test('4 bis. une tâche qui dépasse son estimation ne tombe jamais à zéro', () => {
  const b = bench([{ id: 'A', title: 'coder', est_min: 5 }, { id: 'F', title: 'fin', est_min: 1, final: true }])
  b.on(); b.start('A'); b.go(25)
  assert.ok(E.remainingMin(b.p, E.find(b.p, 'A')) >= 5)
})

test('5. interruption et reprise : état conservé, temps d\'absence non compté', () => {
  const b = bench([{ id: 'A', title: 'a', est_min: 5 }, { id: 'B', title: 'b', est_min: 5 }, { id: 'F', title: 'fin', est_min: 1, final: true }])
  b.on(); b.start('A'); b.go(5); b.done('A'); b.start('B'); b.go(2)
  const pct = b.pct(), act = b.p.activeMs
  const saved = JSON.parse(JSON.stringify(b.p))
  b.now += 8 * 60 * MIN
  b.p = E.resume(saved, b.now)
  assert.equal(b.pct(), pct); assert.equal(b.p.activeMs, act); assert.equal(b.eta().waiting, true)
  b.go(30); assert.equal(b.p.activeMs, act, 'attente non comptée')
  b.on(); b.go(1)
  assert.equal(b.p.activeMs, act + MIN)
  assert.equal(E.resume({ v: 1 }, 0), null); assert.equal(E.resume(null, 0), null); assert.equal(E.resume('x', 0), null)
})

test('5 bis. la mise en veille pendant un tour n\'est pas comptée', () => {
  const b = bench([{ id: 'A', title: 'a' }]); b.on(); b.start('A'); b.go(1)
  b.now += 120 * MIN; b.p = E.tick(b.p, b.now)
  assert.equal(b.p.activeMs, MIN)
})

test('6. parallèle : ni somme, ni division aveugle', () => {
  const inputs = [...['A', 'B', 'C'].map(id => ({ id, title: `coder ${id}`, est_min: 10 })), { id: 'D', title: 'intégrer', est_min: 10, deps: ['A', 'B', 'C'] }, { id: 'F', title: 'fin', est_min: 1, final: true }]
  const rest = p => new Map(p.tasks.map(t => [t.id, t.estMin]))
  const b = bench(inputs)
  assert.equal(E.schedule(b.p, rest(b.p), 1), 41, 'séquentiel')
  assert.equal(E.schedule(b.p, rest(b.p), 3), 21, 'trois voies : 10 + 10 + 1')
  assert.equal(E.schedule(b.p, rest(b.p), 9), 21, 'des voies en plus ne raccourcissent pas la chaîne')
  const par = bench(inputs), seq = bench(inputs)
  par.on('main'); par.on('a1'); par.on('a2'); for (const x of ['A', 'B', 'C']) par.start(x)
  seq.on('main'); seq.start('A')
  par.go(2); seq.go(2)
  assert.ok(par.mid() < seq.mid() * 0.75, `${par.mid()} contre ${seq.mid()}`)
  assert.equal(E.find(par.p, 'A').activeMs, 2 * MIN, 'chaque tâche parallèle reçoit son temps réel')
  par.off('a1'); par.off('a2')
  assert.ok(par.mid() > 20, 'les agents arrêtés, le planning redevient séquentiel')
})

test('listes natives : ré-émission sans remise à zéro', () => {
  let p = E.createProject('x', 'p', [], 0)
  p = E.syncList(p, [{ content: 'Analyser', status: 'in_progress' }, { content: 'Coder', status: 'pending' }, { content: 'Jamais faite', status: 'pending' }], 0)
  p = E.turnStart(p, 'main', 0); p = E.tick(p, 3 * MIN)
  p = E.syncList(p, [{ content: 'Analyser', status: 'completed' }, { content: 'Coder', status: 'in_progress' }, { content: 'Nouvelle étape', status: 'pending' }], 3 * MIN)
  assert.equal(E.find(p, 'Analyser').status, 'done'); assert.equal(E.find(p, 'Jamais faite'), undefined)
  assert.equal(p.samples.length, 1)
  const before = E.percent(p)
  p = E.syncList(p, [{ content: 'Coder', status: 'in_progress' }], 3 * MIN)
  assert.equal(E.find(p, 'Analyser').status, 'done', 'une tâche finie absente de la nouvelle liste reste acquise')
  assert.ok(E.percent(p) >= before)
})

test('blocage, cycle de dépendances, entrées tordues', () => {
  const b = bench([{ id: 'A', title: 'a', deps: ['B'] }, { id: 'B', title: 'b', deps: ['A', 'fantome'] }, { id: 'B', title: 'id en double', weight: -5, est_min: NaN }])
  assert.equal(new Set(b.p.tasks.map(t => t.id)).size, b.p.tasks.length)
  const rest = new Map(b.p.tasks.map(t => [t.id, 1]))
  assert.equal(E.schedule(b.p, rest, 1), b.p.tasks.length, 'aucune tâche perdue par un cycle')
  for (const t of b.p.tasks) if (!t.isFinal) b.p = E.blockTask(b.p, t.id, 0)
  assert.equal(b.txt(), 'projet bloqué')
  assert.equal(E.percent(E.createProject('x', 'vide', [], 0)), 0)
  assert.equal(E.eta(E.createProject('x', 'vide', [], 0), 0).state, 'none')
})

test('affichage du temps', () => {
  const pt = min => E.fmtEta({ state: 'point', min, confidence: 'bonne', waiting: false })
  assert.equal(pt(0.2), '≈ 1 min restante'); assert.equal(pt(6.2), '≈ 6 min restantes'); assert.equal(pt(18), '≈ 18 min restantes')
  assert.equal(pt(44), '≈ 45 min restantes'); assert.equal(pt(100), '≈ 1 h 45 restantes'); assert.equal(pt(120), '≈ 2 h restantes')
  assert.equal(E.fmtEta({ state: 'range', lowMin: 12, highMin: 18, confidence: 'faible', waiting: false }), '≈ 12 à 18 min restantes')
})

test('contrôles reconnus', () => {
  for (const c of ['pytest -q', 'py -3 -m unittest discover', 'npm test', 'npm run build', 'node --test x', 'cd a && npx tsc -p .', 'claude plugin test "x"']) assert.ok(E.isCheck(c), c)
  for (const c of ['ls', 'cat pytest.ini.bak', 'echo latest', 'git commit -m "tests"']) assert.ok(!E.isCheck(c), c)
})

test('session réelle : une preuve obtenue avant la déclaration compte, sauf si un fichier a changé depuis', () => {
  const b = bench([{ id: 'A', title: 'coder', est_min: 3, verify: 'unittest' }, { id: 'F', title: 'fin', est_min: 1, final: true }])
  b.on(); b.start('A'); b.go(1)
  b.cmd('py -3 -m unittest', true); b.go(0.25)
  b.p = E.edited(b.p, 'README.md', b.now)
  assert.equal(E.completeTask(b.p, 'A', '', b.now).ok, true, 'un texte modifié ne périme pas la preuve')
  b.p = E.edited(b.p, 'calc.py', b.now); b.go(0.25)
  assert.equal(b.done('A').ok, false, 'un code modifié la périme')
  b.cmd('py -3 -m unittest', true)
  assert.equal(E.find(b.p, 'A').status, 'done')
  b.start('A')
  assert.equal(b.done('A').ok, true, 'preuve toujours valable')
  b.cmd('py -3 -m unittest', false)
  assert.equal(b.done('A').ok, false, 'un échec annule la preuve')
})

test('session réelle : une seule vérification finale, l’ancienne redevient une tâche ordinaire', () => {
  const b = bench([{ id: 'A', title: 'coder', est_min: 3 }, { id: 'verif', title: 'vérifier', est_min: 2, final: true }])
  b.on(); b.start('A'); b.done('A')
  b.p = E.addTasks(b.p, [{ id: 'verif2', title: 'vérification finale bis', final: true }], b.now)
  assert.deepEqual(b.p.tasks.filter(t => t.isFinal).map(t => t.id), ['verif2'])
  assert.equal(b.p.tasks.at(-1).id, 'verif2')
  b.p = E.dropTask(b.p, 'verif', b.now); assert.equal(E.find(b.p, 'verif').status, 'dropped')
  b.p = E.dropTask(b.p, 'verif2', b.now); assert.notEqual(E.find(b.p, 'verif2').status, 'dropped')
  b.done('verif2'); assert.equal(b.pct(), 100)
})
