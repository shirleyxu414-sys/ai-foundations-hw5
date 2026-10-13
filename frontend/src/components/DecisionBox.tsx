import { useState } from 'react'
import { ApiError } from '../api'

const NAME_KEY = 'campus.approver'

interface Props {
  ticketId: number
  onDecide: (ticketId: number, decidedBy: string, decision: string) => Promise<void>
}

/** A human tells the team how a ticket should end. The agents read it when they work the ticket. */
export default function DecisionBox({ ticketId, onDecide }: Props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const name = localStorage.getItem(NAME_KEY) ?? ''

  const save = async () => {
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      await onDecide(ticketId, name.trim(), text.trim())
      setText('')
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>
        Your decision on #{ticketId}
      </h2>
      <p className="small">
        Optional. If only a person can settle how this ticket ends, write it here. The Boss reads it the next time the team runs.
        {name.trim() === '' && ' Type your name under "Needs a human" first.'}
      </p>
      <textarea
        className="decision"
        rows={3}
        value={text}
        maxLength={1000}
        placeholder="For example: offer the hoodies we have in stock, do not restock."
        onChange={(e) => setText(e.target.value)}
      />
      <button className="btn" disabled={busy || name.trim() === '' || text.trim().length < 3} onClick={save}>
        {busy ? 'Saving…' : 'Record decision'}
      </button>
      {saved && <span className="small"> Saved. The team picks it up on its own; if it does not start, run it again.</span>}
      {error && <p className="small block">{error}</p>}
    </section>
  )
}
