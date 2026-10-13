import { AGENTS, agentLabel, clock, feedItems } from '../derive'
import type { AgentEvent } from '../types'

const ICON: Record<string, string> = {
  start: '▶', asks: '→', uses: '⚙', says: '💬', result: '←', reply: '↩', refused: '⛔', end: '■', error: '!', human: '☺',
}

interface Props {
  runEvents: AgentEvent[]
  filter: string
  onFilter: (name: string) => void
}

/** Everything the agents said and every tool they used, newest first. */
export default function Feed({ runEvents, filter, onFilter }: Props) {
  const items = feedItems(runEvents)
    .filter((i) => filter === 'all' || i.agent === filter)
    .reverse()
  return (
    <section className="panel">
      <h2>
        Live activity
        {filter !== 'all' && <span className="filtered">· {agentLabel(filter)} only</span>}
      </h2>
      <div className="filters">
        <button className={`fchip ${filter === 'all' ? 'on' : ''}`} onClick={() => onFilter('all')}>
          Everyone
        </button>
        {AGENTS.map((a) => (
          <button key={a.name} className={`fchip ${filter === a.name ? 'on' : ''}`} onClick={() => onFilter(a.name)}>
            {a.label}
          </button>
        ))}
      </div>
      <ol className="feed" aria-live="polite">
        {items.map((i) => (
          <li key={i.key} className={`fi ${i.kind}`} style={{ marginLeft: Math.min(i.depth, 3) * 14 }}>
            <span className="ficon" aria-hidden="true">
              {ICON[i.kind]}
            </span>
            <span className="fwho" data-agent={i.agent ?? ''}>{agentLabel(i.agent)}</span>
            <span className="ftext">
              {i.text}
              {i.json && <code className="jsonline">{i.json}</code>}
            </span>
            <span className="ftime mono">{clock(i.time)}</span>
          </li>
        ))}
        {items.length === 0 && <li className="empty">No activity yet. Run the agent team on this ticket.</li>}
      </ol>
    </section>
  )
}
