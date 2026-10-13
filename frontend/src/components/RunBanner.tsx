import { money, statusLabel } from '../derive'
import type { RunOutcome } from '../derive'
import type { Approval, Ticket } from '../types'

interface Props {
  ticket: Ticket
  outcome: RunOutcome
  approvals: Approval[]
  anyRunning: boolean
  starting: boolean
  onRun: () => void
}

export default function RunBanner({ ticket, outcome, approvals, anyRunning, starting, onRun }: Props) {
  const mine = approvals.filter((a) => a.ticket_id === ticket.id)
  const pending = mine.filter((a) => a.status === 'pending')
  const paid = mine.filter((a) => a.status === 'approved')
  const resolved = ticket.state === 'resolved'
  const finished = outcome.state === 'finished'

  let headline: string
  let detail: string
  let tone: string
  if (ticket.running || outcome.state === 'running') {
    headline = 'The agent team is working this ticket…'
    detail = 'Watch the cards below. This page refreshes every second while the agents run.'
    tone = 'working'
  } else if (resolved) {
    headline = 'RESOLVED'
    detail = outcome.decision?.decision ?? 'The Boss closed this ticket.'
    tone = 'resolved'
  } else if (finished) {
    headline = `Run finished · ${statusLabel(ticket).toLowerCase()}`
    tone = 'open'
    if (pending.length > 0)
      detail = `Not resolved yet: ${pending.length} payment${pending.length > 1 ? 's' : ''} (${money(
        pending.reduce((s, a) => s + a.amount, 0),
      )}) waiting for a human to approve. Once that is done, the team picks the ticket up again on its own.`
    else if (paid.length > 0) detail = 'The payment went through. The team carries on from here on its own; if it has not started, run it again.'
    else detail = outcome.decision?.decision ?? 'The Boss left this ticket open.'
  } else if (outcome.state === 'failed') {
    headline = 'The run failed'
    detail = 'See the activity feed for the error. You can start it again.'
    tone = 'failed'
  } else if (outcome.state === 'interrupted') {
    headline = 'The last run stopped before the Boss decided'
    detail = 'The backend may have restarted. You can start it again.'
    tone = 'failed'
  } else {
    headline = 'Not run yet'
    detail = 'Pick the ticket and start the agent team. Nothing is paid or sent until a human approves.'
    tone = 'idle'
  }

  const again = outcome.state !== 'none'
  const disabled = anyRunning || starting || resolved
  // Why the button is off, in a few words (nothing is shown while it can be clicked).
  const reason = starting
    ? 'Starting…'
    : ticket.running
      ? 'The agents are working on this ticket.'
      : anyRunning
        ? 'Another ticket is running. One at a time.'
        : resolved
          ? 'Already resolved. Reset the database to run it again.'
          : null
  return (
    <section className={`panel banner ${tone}`}>
      <div className="bmain">
        <div className="eyebrow">
          Ticket <span className="mono">#{ticket.id}</span> · {ticket.subject} · {ticket.requester}
        </div>
        <h2 className="bhead">{headline}</h2>
        <p>{detail}</p>
        {outcome.tokens !== null && finished && (
          <p className="small">Used about {outcome.tokens.toLocaleString()} tokens in this run.</p>
        )}
      </div>
      <div className="bact">
        <button className="btn primary" disabled={disabled} onClick={onRun}>
          {starting ? 'Starting…' : ticket.running ? 'The agents are working…' : again ? `Run the team again on #${ticket.id}` : `Run the team on #${ticket.id}`}
        </button>
        {disabled && reason && <span className="reason">{reason}</span>}
      </div>
    </section>
  )
}
