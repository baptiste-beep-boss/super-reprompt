// Traduction des événements bruts de Claude Code en signaux pour le moteur. Pur, testable hors Claude Code.
import { isCheck } from './engine'
import type { ListItem } from './engine'

const FAIL = /\b([1-9]\d*) (failed|failures?|failing|errors?)\b|\b(fail|failed|failures|errors)[ =:]+[1-9]\d*|^(FAILED|FAIL)\b|Traceback \(most recent|✖ failing|✘ Validation failed|\[error\]/im
const PASS = /\b\d+ (passed|passing|pass)\b|\bpass [1-9]\d*|^OK\b|\b0 (fail|failed|failures|errors)\b|✔ Validation passed|Test Suites: .*passed/im

// Le code de sortie ment quand la commande est suivie d'un tube (`pytest | tail`) : on lit alors la sortie.
export function verdict(cmd: string, isError: boolean, text: string): 'ok' | 'fail' | 'unknown' {
  if (isError) return 'fail'
  if (!isCheck(cmd)) return 'ok'
  if (FAIL.test(text)) return 'fail'
  const masked = /\|(?!\|)|\|\| *(true|:)|;\s*\S/.test(cmd)
  return !masked || PASS.test(text) ? 'ok' : 'unknown'
}

export type PlanCall = { items?: ListItem[]; advance?: boolean; done?: number[]; start?: number; scope?: string }

// Liste de l'app (update_plan) : soit la liste entière, soit un pas.
export function reduceList(list: ListItem[], c: PlanCall): ListItem[] {
  if (Array.isArray(c.items)) return c.items.map(i => ({ content: String(i.content), status: i.status }))
  let next = list.map(i => ({ ...i }))
  for (const n of c.done ?? []) if (next[n - 1] !== undefined) next[n - 1]!.status = 'completed'
  if (c.start !== undefined && next[c.start - 1] !== undefined) next[c.start - 1]!.status = 'in_progress'
  if (c.advance === true) {
    next = next.map(i => (i.status === 'in_progress' ? { ...i, status: 'completed' } : i))
    const k = next.findIndex(i => i.status === 'pending')
    if (k >= 0) next[k]!.status = 'in_progress'
  }
  return next
}

// Numéro rendu par TaskCreate, pour relier les TaskUpdate suivants.
export const taskNumber = (text: string): string | undefined => /#([\w-]+)/.exec(text)?.[1]
