import test from 'node:test'
import assert from 'node:assert/strict'
import { register } from 'node:module'
// Node n'ajoute pas l'extension aux imports : petit résolveur pour './engine'.
register('data:text/javascript,' + encodeURIComponent(
  "export async function resolve(s,c,n){return n(s.startsWith('./')&&!/\\.[mc]?[jt]sx?$/.test(s)?s+'.ts':s,c)}"), import.meta.url)
const { verdict, reduceList, taskNumber } = await import('../../hooks/bar/signals.ts')

test('un tube ne masque pas un échec', () => {
  assert.equal(verdict('pytest | tail -3', false, '3 failed, 10 passed'), 'fail')
  assert.equal(verdict('pytest | tail -3', false, '13 passed in 2s'), 'ok')
  assert.equal(verdict('pytest | tail -3', false, 'bla'), 'unknown', 'sans preuve lisible, ni réussite ni échec')
  assert.equal(verdict('pytest', false, 'bla'), 'ok', 'sans tube, le code de sortie fait foi')
  assert.equal(verdict('npm test || true', false, ''), 'unknown')
  assert.equal(verdict('node --test x 2>&1 | grep z', false, 'ℹ pass 15\nℹ fail 1'), 'fail')
  assert.equal(verdict('node --test x 2>&1 | grep z', false, 'ℹ pass 16\nℹ fail 0'), 'ok')
  assert.equal(verdict('claude plugin test x | tail', false, ' 2 pass\n 0 fail'), 'ok')
  assert.equal(verdict('py -3 -m unittest', false, 'Ran 213 tests\n\nOK'), 'ok')
  assert.equal(verdict('ls', false, 'errors: 3'), 'ok', 'hors contrôle, on ne lit pas la sortie')
  assert.equal(verdict('ls', true, ''), 'fail')
})

test('liste de l\'app : remplacement, avance, cases, départ', () => {
  const l = reduceList([], { items: ['a', 'b', 'c'].map((content, i) => ({ content, status: i === 0 ? 'in_progress' : 'pending' })) })
  const s = x => x.map(i => i.status[0]).join('')
  assert.equal(s(l), 'ipp')
  assert.equal(s(reduceList(l, { advance: true })), 'cip')
  assert.equal(s(reduceList(l, { done: [1, 2], start: 3 })), 'cci')
  assert.equal(s(reduceList(l, { done: [9], start: 12 })), 'ipp')
  assert.equal(s(l), 'ipp', 'la liste d\'origine n\'est pas modifiée')
})

test('numéro de tâche', () => {
  assert.equal(taskNumber('Task #7 created successfully: x'), '7')
  assert.equal(taskNumber('rien'), undefined)
})
