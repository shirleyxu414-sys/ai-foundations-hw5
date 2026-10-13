import { statusLabel } from '../derive'
import type { Approval, Ticket } from '../types'

interface Props {
  tickets: Ticket[]
  approvals: Approval[]
  selectedId: number | null
  onSelect: (id: number) => void
}

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'customer order',
  rent_notice: 'rent notice',
  price_override: 'price override',
}

export default function TicketList({ tickets, approvals, selectedId, onSelect }: Props) {
  return (
    <section className="panel">
      <h2>
        Tickets on the board
      </h2>
      <div className="tickets">
        {tickets.map((t) => {
          const pending = approvals.filter((a) => a.ticket_id === t.id && a.status === 'pending').length
          return (
            <button
              key={t.id}
              className={`ticket ${t.id === selectedId ? 'on' : ''} ${t.state}`}
              onClick={() => onSelect(t.id)}
              aria-pressed={t.id === selectedId}
            >
              <span className="tid mono">#{t.id}</span>
              <span className="tbody">
                <span className="tsub">{t.subject}</span>
                <span className="tmeta">
                  {t.requester} · {TYPE_LABEL[t.type] ?? t.type}
                </span>
              </span>
              <span className="tbadges">
                {t.running ? (
                  <span className="badge working">AGENTS WORKING</span>
                ) : (
                  <span className={`badge ${t.state === 'resolved' ? 'resolved' : t.status}`}>{statusLabel(t)}</span>
                )}
                {pending > 0 && <span className="badge approval">{pending} to approve</span>}
              </span>
            </button>
          )
        })}
        {tickets.length === 0 && <p className="empty">No tickets yet.</p>}
      </div>
    </section>
  )
}
