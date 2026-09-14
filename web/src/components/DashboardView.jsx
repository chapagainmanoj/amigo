import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Circle, Clock, MessageSquare, Trash2, Plus } from 'lucide-react'
import { apiRequest, supabase } from '../supabase'
import { timeOfDayGreeting } from '../mockData'
import Toast from './Toast'
import ModeChips from './ModeChips'

// apiRequest attaches `status` from the response and `retryable` from the X-Retryable header.
// A rejection carrying neither never reached the API at all, so reporting it as a conflict
// would be wrong twice: it names a cause we did not observe, and it tells the participant to
// refresh when refreshing cannot help. Only 409 means someone else moved this record.
function failureMessage(error, subject) {
  const status = error?.status
  if (status === undefined) return 'Could not reach Amigo — check your connection'
  if (error?.retryable) return `${subject} was busy — try that again`
  if (status === 409) return `${subject} changed elsewhere — refresh and try again`
  if (status >= 500) return `Could not update ${subject.toLowerCase()} — try again shortly`
  return error?.message || `Could not update ${subject.toLowerCase()}`
}

// A reminder whose moment has passed needs an outcome, not a reschedule. Whether delivery
// actually succeeded is our problem, not the participant's: an 'overdue' reminder is one the
// outbox has not sent yet, and leaving it with only Later/Cancel is how stale reminders pile
// up. Done and Skip resolve the Task, and that cancels the still-pending send as part of the
// same transition, so neither state needs a separate Cancel.
// Cancel stays on this branch too. Done and Skip go through resolve_task, which returns
// before its own reminder cleanup when the Task needs no transition, so a Reminder left
// active behind an already-resolved Task cannot be cleared by either one -- Done reports
// success and changes nothing, Skip fails outright. Cancel keys off the Reminder's status
// alone, so it is the only action that clears those rows.
const DUE_STATES = new Set(['delivered', 'overdue'])

export default function DashboardView() {
  const [snapshot, setSnapshot] = useState({
    tasks: { today: [], inbox: [], carried_over: [] },
    progress: { completed: 0, total: 0 },
    reminders: [],
    sessions: [],
  })
  const [toastMsg, setToastMsg] = useState(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [greeting, setGreeting] = useState(timeOfDayGreeting())

  const fetchSnapshot = useCallback(async () => {
    const nextSnapshot = await apiRequest('/api/dashboard/snapshot')
    setSnapshot(nextSnapshot)
  }, [])

  const tasks = snapshot.tasks.today
  const inboxTasks = snapshot.tasks.inbox
  const carriedTasks = snapshot.tasks.carried_over
  const reminders = snapshot.reminders
  const sessions = snapshot.sessions

  useEffect(() => {
    // Update greeting if they keep it open across day boundaries
    const interval = setInterval(() => setGreeting(timeOfDayGreeting()), 60000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchSnapshot()

    // Realtime channel subscriptions
    const tasksChannel = supabase
      .channel('tasks-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, () => {
        fetchSnapshot()
      })
      .subscribe()

    const remindersChannel = supabase
      .channel('reminders-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'reminders' }, () => {
        fetchSnapshot()
      })
      .subscribe()

    const sessionsChannel = supabase
      .channel('sessions-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'sessions' }, () => {
        fetchSnapshot()
      })
      .subscribe()

    return () => {
      supabase.removeChannel(tasksChannel)
      supabase.removeChannel(remindersChannel)
      supabase.removeChannel(sessionsChannel)
    }
  }, [fetchSnapshot])

  const handleResolveTask = async (task, outcome) => {
    if (task.status && task.status !== 'pending') return

    try {
      const result = await apiRequest(`/api/tasks/${task.task_id}/resolve`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ outcome, expected_version: task.version }),
      })
      // resolve_task reports `transitioned: false` when the Task was already in the requested
      // state. Nothing moved, and its Reminders were never reached, so saying "Task completed"
      // would explain a list that visibly did not change.
      if (result?.transitioned === false) {
        setToastMsg('That Task was already resolved — use Cancel to clear the reminder')
      } else {
        setToastMsg(
          outcome === 'completed'
            ? 'Task completed'
            : outcome === 'skipped'
              ? 'Task skipped'
              : 'Task cancelled',
        )
      }
      await fetchSnapshot()
    } catch (error) {
      setToastMsg(failureMessage(error, 'Task'))
    }
  }

  const handleAddTask = async (e) => {
    e.preventDefault()
    if (!newTaskTitle.trim()) return

    try {
      await apiRequest('/api/tasks', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ title: newTaskTitle, category: 'other' }),
      })
      setNewTaskTitle('')
      setToastMsg('Task added to Inbox')
      await fetchSnapshot()
    } catch (error) {
      setToastMsg(failureMessage(error, 'Task'))
    }
  }

  const handleSnooze = async (reminder) => {
    try {
      const result = await apiRequest(`/api/reminders/${reminder.reminder_id}/later`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ expected_task_version: reminder.task.version }),
      })
      setToastMsg(
        `Next: ${result.intended_local_date} ${result.intended_local_time.slice(0, 5)} ${result.intended_timezone}`,
      )
      await fetchSnapshot()
    } catch (error) {
      setToastMsg(failureMessage(error, 'Reminder'))
    }
  }

  const handleCancelReminder = async (reminder) => {
    try {
      await apiRequest(`/api/reminders/${reminder.reminder_id}`, {
        method: 'DELETE',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
      setToastMsg('Reminder cancelled')
      await fetchSnapshot()
    } catch (error) {
      setToastMsg(failureMessage(error, 'Reminder'))
    }
  }

  const doneCount = snapshot.progress.completed
  const totalCount = snapshot.progress.total

  return (
    <div className="animate-slide-in">
      {/* Daily Horizon Card (Glass) */}
      <div className="horizon-card">
        <div className="horizon-copy">
          <h1 className="horizon-greeting">{greeting.headline}</h1>
          <p className="horizon-subtext">{greeting.subtext}</p>
          <div className="horizon-progress-pill">
            <CheckCircle2 size={16} color="var(--ok)" />
            <span>
              <strong>{doneCount}</strong> of {totalCount} done today
            </span>
          </div>
        </div>
      </div>

      <ModeChips />

      <div className="dashboard-grid">
        {/* Main Column: Tasks */}
        <section>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px',
            }}
          >
            <h2 className="display-text" style={{ fontSize: '1.5rem' }}>
              Tasks
            </h2>
          </div>

          <div className="flat-card" style={{ padding: '24px' }}>
            <form
              onSubmit={handleAddTask}
              style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}
            >
              <input
                type="text"
                placeholder="Add a new task..."
                value={newTaskTitle}
                onChange={(e) => setNewTaskTitle(e.target.value)}
                style={{ flex: 1, backgroundColor: 'var(--oat)', border: '1px solid var(--rule)' }}
              />
              <button
                type="submit"
                className="btn-primary"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 16px',
                }}
              >
                <Plus size={20} />
              </button>
            </form>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {tasks.map((task) => (
                <div
                  key={task.task_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '12px',
                    background: 'var(--oat)',
                    border: '1px solid var(--rule)',
                    borderRadius: '8px',
                    opacity: task.status === 'completed' ? 0.6 : 1,
                    transition: 'opacity 0.2s ease',
                  }}
                >
                  <button
                    onClick={() => handleResolveTask(task, 'completed')}
                    disabled={task.status !== 'pending'}
                    aria-label={task.status === 'completed' ? 'Task completed' : 'Mark task done'}
                    style={{
                      background: 'transparent',
                      color: task.status === 'completed' ? 'var(--ok)' : 'var(--ink-2)',
                      marginRight: '12px',
                      flexShrink: 0,
                    }}
                  >
                    {task.status === 'completed' ? (
                      <CheckCircle2 size={24} className="animate-pop" />
                    ) : (
                      <Circle size={24} />
                    )}
                  </button>
                  <span
                    style={{
                      flex: 1,
                      textDecoration: task.status === 'completed' ? 'line-through' : 'none',
                      color: task.status === 'completed' ? 'var(--ink-2)' : 'var(--ink)',
                    }}
                  >
                    {task.title}
                  </span>
                  {task.status === 'pending' && (
                    <button
                      onClick={() => handleResolveTask(task, 'skipped')}
                      style={{
                        background: 'transparent',
                        color: 'var(--ink-2)',
                        padding: '4px 8px',
                      }}
                    >
                      Skip
                    </button>
                  )}
                  <button
                    onClick={() => handleResolveTask(task, 'cancelled')}
                    disabled={task.status !== 'pending'}
                    aria-label="Cancel task"
                    style={{ background: 'transparent', color: 'var(--ink-2)', padding: '4px' }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              {tasks.length === 0 && (
                <div style={{ color: 'var(--ink-2)', textAlign: 'center', padding: '24px 0' }}>
                  No tasks pending.
                </div>
              )}
            </div>
          </div>

          <h2 className="display-text" style={{ fontSize: '1.25rem', margin: '24px 0 12px' }}>
            Inbox
          </h2>
          <div className="flat-card" style={{ padding: '16px' }}>
            {inboxTasks.map((task) => (
              <div
                key={task.task_id}
                style={{
                  padding: '12px',
                  background: 'var(--oat)',
                    border: '1px solid var(--rule)',
                  borderRadius: '8px',
                  marginBottom: '8px',
                }}
              >
                {task.title}
              </div>
            ))}
            {inboxTasks.length === 0 && (
              <div style={{ color: 'var(--ink-2)', textAlign: 'center', padding: '12px 0' }}>
                Inbox is clear.
              </div>
            )}
          </div>

          <h2 className="display-text" style={{ fontSize: '1.25rem', margin: '24px 0 12px' }}>
            Carried over
          </h2>
          <div className="flat-card" style={{ padding: '16px' }}>
            {carriedTasks.map((task) => (
              <div key={task.task_id} style={{ padding: '12px' }}>
                {task.title} <span style={{ color: 'var(--ink-2)' }}>· from {task.due_date}</span>
              </div>
            ))}
            {carriedTasks.length === 0 && (
              <div style={{ color: 'var(--ink-2)', textAlign: 'center', padding: '12px 0' }}>
                Nothing carried over.
              </div>
            )}
          </div>
        </section>

        {/* Sidebar Column: Reminders & Sessions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <section>
            <h2 className="display-text" style={{ fontSize: '1.25rem', marginBottom: '16px' }}>
              Active Reminders
            </h2>
            <div
              className="flat-card"
              style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}
            >
              {reminders.map((rem) => (
                <div
                  key={rem.reminder_id}
                  style={{ padding: '12px', background: 'var(--oat)',
                    border: '1px solid var(--rule)', borderRadius: '8px' }}
                >
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}
                  >
                    <Clock size={14} color="var(--signal-deep)" />
                    <span style={{ fontSize: '0.85rem', color: 'var(--signal-deep)' }}>
                      {rem.intended_local_date} {rem.intended_local_time.slice(0, 5)}{' '}
                      {rem.intended_timezone} · {rem.delivery_state}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.95rem', marginBottom: '12px' }}>
                    {rem.task.title}
                    {rem.task.population === 'carried_over' && ' · carried over'}
                  </div>
                  {DUE_STATES.has(rem.delivery_state) ? (
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      <button
                        onClick={() => handleResolveTask(rem.task, 'completed')}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Done
                      </button>
                      <button
                        onClick={() => handleResolveTask(rem.task, 'skipped')}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Skip
                      </button>
                      <button
                        onClick={() => handleSnooze(rem)}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Later
                      </button>
                      <button
                        onClick={() => handleCancelReminder(rem)}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        onClick={() => handleSnooze(rem)}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Later
                      </button>
                      <button
                        onClick={() => handleCancelReminder(rem)}
                        className="btn-minimal"
                        style={{ flex: 1 }}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {reminders.length === 0 && (
                <div style={{ color: 'var(--ink-2)', fontSize: '0.9rem' }}>
                  No active reminders.
                </div>
              )}
            </div>
          </section>

          <section>
            <h2 className="display-text" style={{ fontSize: '1.25rem', marginBottom: '16px' }}>
              Recent Sessions
            </h2>
            <div
              className="flat-card"
              style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}
            >
              {sessions.map((sess) => (
                <div
                  key={sess.session_id}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'flex-start',
                    paddingBottom: '12px',
                    borderBottom: '1px solid var(--rule)',
                  }}
                >
                  <MessageSquare size={16} color="var(--ink-2)" style={{ marginTop: '4px' }} />
                  <div>
                    <div style={{ fontSize: '0.9rem', marginBottom: '4px' }}>
                      {sess.label}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        gap: '8px',
                        fontSize: '0.8rem',
                        color: 'var(--ink-2)',
                      }}
                    >
                      <span>{new Date(sess.started_at).toLocaleString()}</span>
                      <span>•</span>
                      <span>{sess.duration_minutes}m</span>
                      <span>•</span>
                      <span style={{ color: 'var(--signal-deep)' }}>{sess.session_type_label}</span>
                    </div>
                  </div>
                </div>
              ))}
              {sessions.length === 0 && (
                <div style={{ color: 'var(--ink-2)', fontSize: '0.9rem' }}>
                  No recent sessions.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
      <Toast message={toastMsg} onClose={() => setToastMsg(null)} />
    </div>
  )
}
