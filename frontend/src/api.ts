import type { Approval, Cash, Continued, EventsPage, Payment, Received, ResetResult, RunStarted, Ticket } from './types'

// The backend from Problem 7: `uvicorn main:app --reload --port 8000` in backend/.
const BASE: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, init)
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${BASE}. Is it running?`)
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      const detail = body?.detail
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((d) => d.msg).join('; ')
    } catch {
      /* keep the status text */
    }
    throw new ApiError(res.status, message)
  }
  return (await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const api = {
  tickets: () => request<Ticket[]>('/api/tickets'),
  runTicket: (id: number) => post<RunStarted>(`/api/tickets/${id}/run`),
  events: (params: { ticketId?: number; after?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params.ticketId !== undefined) q.set('ticket_id', String(params.ticketId))
    if (params.after !== undefined) q.set('after', String(params.after))
    q.set('limit', String(params.limit ?? 500))
    return request<EventsPage>(`/api/events?${q}`)
  },
  approvals: () => request<Approval[]>('/api/approvals'),
  approve: (id: number, approvedBy: string) =>
    post<Payment>(`/api/approvals/${id}/approve`, { approved_by: approvedBy }),
  decline: (id: number, declinedBy: string) =>
    post<Continued & { ok: boolean; approval_id: number; status: string; declined_by: string }>(`/api/approvals/${id}/decline`, { declined_by: declinedBy }),
  receive: (id: number, receivedBy: string) => post<Received>(`/api/approvals/${id}/receive`, { received_by: receivedBy }),
  decide: (ticketId: number, decidedBy: string, decision: string) =>
    post<Continued & { ok: boolean }>(`/api/tickets/${ticketId}/decision`, { decided_by: decidedBy, decision }),
  cash: () => request<Cash>('/api/cash'),
  reset: () => post<ResetResult>('/api/reset'),
}
