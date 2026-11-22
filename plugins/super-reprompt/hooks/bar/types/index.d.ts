export type BarView = { percent: number; text: string }
declare module 'claude-code' {
  interface PluginState {
    'super-reprompt': { bar: BarView | null }
  }
}
