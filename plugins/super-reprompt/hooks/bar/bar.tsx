// Composant graphique seul : il ne connaît que { percent, text }. Aucun calcul de progression ici.
import type { BarView } from '../types'

// Gris neutres translucides, lisibles en clair comme en sombre.
export function track(percent: number, width: number): string {
  const p = Math.max(0, Math.min(100, percent))
  const fill = p === 0 ? 0 : Math.max(4, Math.round((width * p) / 100))
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="20" viewBox="0 0 ${width} 20">` +
    `<rect x="0" y="8.5" width="${width}" height="3" rx="1.5" fill="#9a9a9a" fill-opacity=".22"/>` +
    `<rect x="0" y="8.5" width="${fill}" height="3" rx="1.5" fill="#b4b4b4" fill-opacity=".9"/></svg>`
}

// Une seule ligne : c'est la hauteur minimale du bandeau de l'app (40 px, marges comprises). 650 px au plus.
export function drawBar(ui: any, surface: string, columns: number, v: BarView) {
  const { Box, Text, Svg } = ui
  const pct = `${v.percent} %`
  if (surface !== 'terminal' && Svg !== undefined) {
    const width = Math.round(Math.max(90, Math.min(360, columns * 7 - 270)))
    return (
      <Box flexDirection="row" alignItems="center" justifyContent="center" gap="md" width="100%">
        <Svg source={track(v.percent, width)} alt={`Projet : ${pct}${v.text === '' ? '' : `, ${v.text}`}`} width={width} height={20} />
        <Text size="caption" weight="medium" tabular wrap="truncate-end">{pct}</Text>
        {v.text === '' ? null : <Text size="caption" dimColor tabular wrap="truncate-end">{`|  ◷ ${v.text}`}</Text>}
      </Box>
    )
  }
  const cells = Math.max(8, Math.min(40, columns - 40))
  const on = Math.round((cells * v.percent) / 100)
  return (
    <Box flexDirection="row">
      <Text>{'━'.repeat(on)}</Text>
      <Text dimColor>{'─'.repeat(cells - on)}</Text>
      <Text>{` ${pct}`}</Text>
      {v.text === '' ? null : <Text dimColor>{` | ◷ ${v.text}`}</Text>}
    </Box>
  )
}
