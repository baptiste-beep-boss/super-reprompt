// Pertinence de l'estimation : 400 projets simulés, durées réelles = estimation x biais du projet x aléa.
// Compare au temps réellement restant, et à la règle de trois que l'on refuse.
import * as E from '../../hooks/bar/engine.ts'
let s = 12345
const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32)
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd())
const KINDS = ['analyse', 'code', 'test', 'document', 'integration']
const err = { moteur: {}, regle3: {} }, inside = {}, count = {}
for (let k = 0; k < 400; k++) {
  const n = 6 + Math.floor(rnd() * 30), bias = Math.exp(0.6 * gauss())
  const est = Array.from({ length: n }, () => 1 + rnd() * 14)
  const act = est.map(e => Math.max(0.2, e * bias * Math.exp(0.35 * gauss())))
  let now = 0
  let p = E.createProject('x', 'x', est.map((e, i) => ({ id: `t${i}`, title: `t ${i}`, kind: KINDS[i % 5], est_min: e, deps: i ? [`t${i - 1}`] : [] })), 0)
  p = E.turnStart(p, 'main', 0)
  const seen = new Set()
  for (let i = 0; i < n; i++) {
    p = E.startTask(p, `t${i}`, now)
    for (let m = 0; m < act[i] * 4; m++) { now += 15000; p = E.tick(p, now) }
    p = E.completeTask(p, `t${i}`, 'ok', now).p
    const pct = E.percent(p), left = act.slice(i + 1).reduce((a, b) => a + b, 0) + 2 * bias
    for (const mark of [10, 25, 50, 75]) if (pct >= mark && !seen.has(mark) && i < n - 1) {
      seen.add(mark)
      const e = E.eta(p, now)
      if (e.state !== 'point' && e.state !== 'range') continue
      const mid = e.state === 'point' ? e.min : Math.sqrt(e.lowMin * e.highMin)
      const r3 = (now / 60000) * (100 - pct) / pct
      ;(err.moteur[mark] ??= []).push(Math.abs(mid - left) / left)
      ;(err.regle3[mark] ??= []).push(Math.abs(r3 - left) / left)
      if (e.state === 'range') { count[mark] = (count[mark] ?? 0) + 1; inside[mark] = (inside[mark] ?? 0) + (left >= e.lowMin && left <= e.highMin ? 1 : 0) }
    }
  }
}
const med = xs => xs.sort((a, b) => a - b)[Math.floor(xs.length / 2)]
for (const m of [10, 25, 50, 75]) console.log(`${m} % : erreur médiane moteur ${(med(err.moteur[m]) * 100).toFixed(0)} %, règle de trois ${(med(err.regle3[m]) * 100).toFixed(0)} %` + (count[m] ? `, vrai temps dans la plage ${Math.round(100 * inside[m] / count[m])} % (n=${count[m]})` : ''))
