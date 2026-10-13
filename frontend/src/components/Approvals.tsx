import { useEffect, useState } from 'react'
import { ApiError } from '../api'
import { approvalTitle, money } from '../derive'
import type { Approval, Payment } from '../types'

const NAME_KEY = 'campus.approver'

interface Props {
  approvals: Approval[]
  balance: number | undefined
  onApprove: (id: number, approvedBy: string) => Promise<Payment>
  onDecline: (id: number, declinedBy: string) => Promise<void>
  onReceive: (id: number, receivedBy: string) => Promise<void>
  onSelectTicket: (id: number) => void
}

function Card({ a, name, balance, onApprove, onDecline, onSelectTicket }: { a: Approval } & Omit<Props, 'approvals' | 'onReceive'> & { name: string }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const short = balance !== undefined && a.amount > balance

  useEffect(() => {
    if (!confirm) return
    const t = window.setTimeout(() => setConfirm(false), 5000)
    return () => window.clearTimeout(t)
  }, [confirm])

  const click = async () => {
    if (!confirm) return setConfirm(true)
    setConfirm(false)
    setBusy(true)
    setError(null)
    try {
      await onApprove(a.id, name.trim())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const decline = async () => {
    setBusy(true)
    setError(null)
    try {
      await onDecline(a.id, name.trim())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="appr">
      <div className="ahead2">
        <b>{approvalTitle(a)}</b>
        <span className="amount mono">{money(a.amount)}</span>
      </div>
      <p className="small">{a.reason}</p>
      <p className="small">
        Prepared by {a.requested_by ?? 'an agent'}
        {a.ticket_id !== null && (
          <>
            {' '}
            for{' '}
            <button className="linkbtn" onClick={() => onSelectTicket(a.ticket_id as number)}>
              ticket #{a.ticket_id}
            </button>
          </>
        )}
        . No money has moved.
      </p>
      {short && <p className="small block">Not enough cash: checking has {money(balance as number)}.</p>}
      {error && <p className="small block">{error}</p>}
      <button className={`btn primary ${confirm ? 'confirm' : ''}`} disabled={busy || short || name.trim() === ''} onClick={click}>
        {busy ? 'Paying…' : confirm ? `Confirm: pay ${money(a.amount)}` : `Approve ${money(a.amount)}`}
      </button>
      <button className="btn ghost decline" disabled={busy || name.trim() === ''} onClick={decline} title="Say no to this payment. No money moves.">
        Decline
      </button>
      {name.trim() === '' && <span className="small"> Type your name above first.</span>}
    </li>
  )
}

export default function Approvals({ approvals, balance, onApprove, onDecline, onReceive, onSelectTicket }: Props) {
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) ?? '')
  useEffect(() => localStorage.setItem(NAME_KEY, name), [name])
  const pending = approvals.filter((a) => a.status === 'pending')
  const onTheWay = approvals.filter((a) => a.kind === 'purchase_order' && a.status === 'approved' && !a.received_at)
  const done = approvals.filter((a) => a.status !== 'pending').slice(-4).reverse()
  const approved = approvals.filter((a) => a.status === 'approved')
  const approvedTotal = approved.reduce((sum, a) => sum + a.amount, 0)
  const [receiving, setReceiving] = useState<number | null>(null)
  const [receiveError, setReceiveError] = useState<string | null>(null)
  const receive = async (id: number) => {
    setReceiving(id)
    setReceiveError(null)
    try {
      await onReceive(id, name.trim())
    } catch (e) {
      setReceiveError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setReceiving(null)
    }
  }

  return (
    <section className="panel">
      <h2>
        Needs a human
      </h2>
      <p className="small">The agents only prepare payments. Approving here is what actually moves the cash. The team then carries on with the ticket by itself.</p>
      <label className="who">
        Your name
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="who is approving?" maxLength={60} />
      </label>
      <ul className="apprs">
        {pending.map((a) => (
          <Card key={a.id} a={a} name={name} balance={balance} onApprove={onApprove} onDecline={onDecline} onSelectTicket={onSelectTicket} />
        ))}
        {pending.length === 0 && <li className="empty">Nothing waiting for approval.</li>}
      </ul>
      {onTheWay.length > 0 && (
        <>
          <h3>Paid orders on the way</h3>
          <p className="small">When the delivery actually arrives, confirm it here. Stock goes up and the agents can see it.</p>
          <ul className="apprs">
            {onTheWay.map((a) => (
              <li key={a.id} className="appr arrived">
                <div className="ahead2">
                  <b>
                    {a.qty ?? '?'} × {a.sku ?? 'item'}
                  </b>
                  <span className="mono small">order {a.id}</span>
                </div>
                <p className="small">
                  Paid {money(a.amount)}
                  {a.ticket_id !== null && ` for ticket #${a.ticket_id}`}. Not received yet.
                </p>
                <button className="btn" disabled={receiving === a.id || name.trim() === ''} onClick={() => receive(a.id)}>
                  {receiving === a.id ? 'Saving…' : 'Mark received'}
                </button>
              </li>
            ))}
          </ul>
          {receiveError && <p className="small block">{receiveError}</p>}
        </>
      )}
      {done.length > 0 && (
        <>
          <h3>Done</h3>
          <ul className="doneList">
            {done.map((a) => (
              <li key={a.id}>
                <span className={`badge ${a.status}`}>{a.status.toUpperCase()}</span> {approvalTitle(a)} · {money(a.amount)}
              </li>
            ))}
          </ul>
          {approved.length > 0 && (
            <p className="approved-total">
              Total approved: <b className="mono">{money(approvedTotal)}</b>
              {approved.length > done.filter((a) => a.status === 'approved').length && ` across ${approved.length} approvals`}
            </p>
          )}
        </>
      )}
    </section>
  )
}
