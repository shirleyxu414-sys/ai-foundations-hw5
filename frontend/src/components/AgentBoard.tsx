import { AGENTS, agentLabel, agentView, plain, statusWords, summariesFor, toolLabel } from '../derive'
import type { RunState } from '../derive'
import type { AgentEvent } from '../types'

interface Props {
  runEvents: AgentEvent[]
  filter: string
  onFilter: (name: string) => void
}

/** One card per agent: whether it is working, what it is doing now, and what it last said. */
export function AgentBoard({ runEvents, filter, onFilter }: Props) {
  return (
    <section className="panel">
      <h2>
        The agent team
      </h2>
      <div className="agents-wrap">
      <div className="agents">
        {AGENTS.map((a) => {
          const v = agentView(runEvents, a.name)
          return (
            <button
              key={a.name}
              className={`agent a-${a.name} ${v.state} ${filter === a.name ? 'picked' : ''}`}
              onClick={() => onFilter(filter === a.name ? 'all' : a.name)}
              aria-pressed={filter === a.name}
            >
              <span className="ahead">
                <span className="glyph">{a.glyph}</span>
                <span className="aname">
                  {a.label}
                  <small>{a.role}</small>
                </span>
                <span className={`pill ${v.state}`}>{v.state === 'working' ? 'WORKING' : v.state === 'done' ? 'DONE' : 'IDLE'}</span>
              </span>
              <span className="abody">
                <span className="doing">
                  <b>Status:</b> {v.doing}
                  {v.turns > 1 && <span className="turns"> · asked {v.turns}×</span>}
                </span>
                <span className="said">
                  <b>Said:</b> {v.said ? v.said : <i>nothing yet</i>}
                </span>
                <span className="chips">
                  {v.tools.map((t) => (
                    <span key={t} className="chip">
                      {toolLabel(t)}
                    </span>
                  ))}
                </span>
              </span>
            </button>
          )
        })}
      </div>
      </div>
      <p className="hint">
        {filter === 'all' ? (
          'Click an agent to show only its activity below. Click it again to show everyone.'
        ) : (
          <>
            Showing only <b>{agentLabel(filter)}</b> in Live activity below.{' '}
            <button className="linkbtn" onClick={() => onFilter('all')}>
              Show everyone
            </button>
          </>
        )}
      </p>
    </section>
  )
}

/** A short summary of what each agent did on this ticket, filled in as each one finishes. */
export function Summaries({ runEvents, runState }: { runEvents: AgentEvent[]; runState: RunState }) {
  const rows = AGENTS.map((a) => ({ a, items: summariesFor(runEvents, a.name), view: agentView(runEvents, a.name) }))
  // Why an agent has nothing to show yet, in plain words.
  const noteFor = (state: string): string =>
    state === 'working' ? 'Working on it now…' : runState === 'running' ? 'Not called yet' : runState === 'none' ? 'Not run yet' : 'Did not work on this ticket'
  return (
    <section className="panel">
      <h2>What each agent did</h2>
      <div className="summaries-wrap">
      <div className="summaries">
        {rows.map(({ a, items, view }) =>
          items.length === 0 ? (
            <article key={a.name} className={`summary summary-empty a-${a.name}`}>
              <h3>
                <span className="glyph">{a.glyph}</span> {a.label}
              </h3>
              <p className="empty-note">{noteFor(view.state)}</p>
            </article>
          ) : (
            <article key={a.name} className={`summary a-${a.name}`}>
              <h3>
                <span className="glyph">{a.glyph}</span> {a.label}
              </h3>
              {items.map((s) => (
                <div key={s.invocation} className="turn">
                  {s.decision && (
                    <>
                      <p>
                        <b>Decision:</b> {plain(s.decision.decision)}
                      </p>
                      <p className="small">
                        Ticket set to <b>{statusWords(s.decision.status)}</b> · worked with {s.decision.owners.map((o) => agentLabel(o)).join(', ')}
                      </p>
                      <p className="small">{plain(s.decision.reasoning)}</p>
                    </>
                  )}
                  {s.report && (
                    <>
                      <p>{plain(s.report.summary)}</p>
                      {s.report.actions_taken.length > 0 && (
                        <ul>
                          {s.report.actions_taken.map((x, i) => (
                            <li key={i}>{plain(x)}</li>
                          ))}
                        </ul>
                      )}
                      {s.report.needs_human_approval.length > 0 && (
                        <p className="small need">
                          <b>Needs a human:</b> {plain(s.report.needs_human_approval.join(' · '))}
                        </p>
                      )}
                      {s.report.blockers.length > 0 && (
                        <p className="small block">
                          <b>Blocked by:</b> {plain(s.report.blockers.join(' · '))}
                        </p>
                      )}
                    </>
                  )}
                </div>
              ))}
              {view.tools.length > 0 && (
                <p className="chips">
                  {view.tools.map((t) => (
                    <span key={t} className="chip">
                      {toolLabel(t)}
                    </span>
                  ))}
                </p>
              )}
            </article>
          ),
        )}
      </div>
      </div>
    </section>
  )
}
