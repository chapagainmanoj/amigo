import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Circle, Clock, MessageSquare, Trash2, Plus } from 'lucide-react'
import { apiRequest, supabase } from '../supabase'
import { timeOfDayGreeting } from '../mockData'
import Toast from './Toast'
import ModeChips from './ModeChips'

export default function DashboardView({ pairedUser }) {
  const [tasks, setTasks] = useState([])
  const [inboxTasks, setInboxTasks] = useState([])
  const [reminders, setReminders] = useState([])
  const [sessions, setSessions] = useState([])
  const [toastMsg, setToastMsg] = useState(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [greeting, setGreeting] = useState(timeOfDayGreeting())

  const tz = pairedUser?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone

  const getLocalDateString = useCallback(() => {
    try {
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: tz,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      })
      const parts = formatter.formatToParts(new Date())
      const month = parts.find((p) => p.type === 'month').value
      const day = parts.find((p) => p.type === 'day').value
      const year = parts.find((p) => p.type === 'year').value
      return `${year}-${month}-${day}`
    } catch {
      return new Date().toISOString().split('T')[0]
    }
  }, [tz])

  const fetchTasks = useCallback(async () => {
    const todayStr = getLocalDateString()
    const { data, error } = await supabase
      .from('tasks')
      .select('*')
      .eq('due_date', todayStr)
      .order('created_at', { ascending: false })
    if (!error && data) {
      setTasks(data)
    }
  }, [getLocalDateString])

  const fetchInboxTasks = useCallback(async () => {
    const { data, error } = await supabase
      .from('tasks')
      .select('*')
      .is('due_date', null)
      .eq('status', 'pending')
      .order('created_at', { ascending: false })
    if (!error && data) {
      setInboxTasks(data)
    }
  }, [])

  const fetchReminders = useCallback(async () => {
    const { data, error } = await supabase
      .from('reminders')
      .select('*, tasks(title, category, version)')
      .eq('status', 'pending')
      .order('scheduled_time', { ascending: true })
    if (!error && data) {
      const mapped = data.map((r) => {
        const timeVal = new Date(r.scheduled_time)
        const timeStr = timeVal.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        return {
          id: r.reminder_id,
          label: r.tasks?.title || 'Reminder',
          time: timeStr,
          scheduled_time: r.scheduled_time,
          task_version: r.tasks?.version,
        }
      })
      setReminders(mapped)
    }
  }, [])

  const fetchSessions = useCallback(async () => {
    const { data, error } = await supabase
      .from('sessions')
      .select('*')
      .order('started_at', { ascending: false })
      .limit(5)
    if (!error && data) {
      const mapped = data.map((s) => {
        const durationStr = s.ended_at
          ? `${Math.round((new Date(s.ended_at) - new Date(s.started_at)) / 60000)}m`
          : 'ongoing'
        const start = new Date(s.started_at)
        const diffHrs = (new Date() - start) / 3600000
        const relativeTime =
          diffHrs < 24 ? `${Math.round(diffHrs)} hours ago` : start.toLocaleDateString()
        return {
          id: s.session_id,
          summary:
            s.context_summary ||
            (s.ended_at ? 'Ended session' : 'Current active conversation'),
          timestamp: relativeTime,
          duration: durationStr,
          mood: s.session_type || 'Casual',
        }
      })
      setSessions(mapped)
    }
  }, [])

  useEffect(() => {
    // Update greeting if they keep it open across day boundaries
    const interval = setInterval(() => setGreeting(timeOfDayGreeting()), 60000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchTasks()
    fetchInboxTasks()
    fetchReminders()
    fetchSessions()

    // Realtime channel subscriptions
    const tasksChannel = supabase
      .channel('tasks-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, () => {
        fetchTasks()
        fetchInboxTasks()
      })
      .subscribe()

    const remindersChannel = supabase
      .channel('reminders-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'reminders' }, () => {
        fetchReminders()
      })
      .subscribe()

    const sessionsChannel = supabase
      .channel('sessions-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'sessions' }, () => {
        fetchSessions()
      })
      .subscribe()

    return () => {
      supabase.removeChannel(tasksChannel)
      supabase.removeChannel(remindersChannel)
      supabase.removeChannel(sessionsChannel)
    }
  }, [fetchInboxTasks, fetchReminders, fetchSessions, fetchTasks])

  const handleResolveTask = async (task, outcome) => {
    if (task.status !== 'pending') return

    try {
      await apiRequest(`/api/tasks/${task.task_id}/resolve`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ outcome, expected_version: task.version }),
      })
      setToastMsg(
        outcome === 'completed'
          ? 'Task completed'
          : outcome === 'skipped'
            ? 'Task skipped'
            : 'Task cancelled',
      )
      await Promise.all([fetchTasks(), fetchInboxTasks(), fetchReminders()])
    } catch {
      setToastMsg('Task changed elsewhere — refresh and try again')
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
      await fetchInboxTasks()
    } catch {
      setToastMsg('Failed to add task')
    }
  }

  const handleSnooze = async (reminder) => {
    try {
      const result = await apiRequest(`/api/reminders/${reminder.id}/later`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ expected_task_version: reminder.task_version }),
      })
      setToastMsg(
        `Next: ${result.intended_local_date} ${result.intended_local_time.slice(0, 5)} ${result.intended_timezone}`,
      )
      await fetchReminders()
    } catch {
      setToastMsg('Failed to snooze reminder')
    }
  }

  const doneCount = tasks.filter((task) => task.status === 'completed').length
  const totalCount = tasks.length

  return (
    <div className="animate-slide-in">
      {/* Daily Horizon Card (Glass) */}
      <div className="horizon-card">
        <div className="horizon-copy">
          <h1 className="horizon-greeting">{greeting.headline}</h1>
          <p className="horizon-subtext">{greeting.subtext}</p>
          <div className="horizon-progress-pill">
            <CheckCircle2 size={16} color="var(--ember)" />
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
                style={{ flex: 1, backgroundColor: 'rgba(255,255,255,0.03)' }}
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
                    background: 'rgba(255,255,255,0.02)',
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
                      color: task.status === 'completed' ? 'var(--ember)' : 'var(--mist)',
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
                      color: task.status === 'completed' ? 'var(--mist)' : 'var(--paper)',
                    }}
                  >
                    {task.title}
                  </span>
                  {task.status === 'pending' && (
                    <button
                      onClick={() => handleResolveTask(task, 'skipped')}
                      style={{
                        background: 'transparent',
                        color: 'var(--mist)',
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
                    style={{ background: 'transparent', color: 'var(--mist)', padding: '4px' }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              {tasks.length === 0 && (
                <div style={{ color: 'var(--mist)', textAlign: 'center', padding: '24px 0' }}>
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
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: '8px',
                  marginBottom: '8px',
                }}
              >
                {task.title}
              </div>
            ))}
            {inboxTasks.length === 0 && (
              <div style={{ color: 'var(--mist)', textAlign: 'center', padding: '12px 0' }}>
                Inbox is clear.
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
                  key={rem.id}
                  style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px' }}
                >
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}
                  >
                    <Clock size={14} color="var(--gold)" />
                    <span style={{ fontSize: '0.85rem', color: 'var(--gold)' }}>
                      {rem.time}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.95rem', marginBottom: '12px' }}>
                    {rem.label}
                  </div>
                  <button
                    onClick={() => handleSnooze(rem)}
                    className="btn-secondary"
                    style={{ width: '100%', fontSize: '0.85rem' }}
                  >
                    Later
                  </button>
                </div>
              ))}
              {reminders.length === 0 && (
                <div style={{ color: 'var(--mist)', fontSize: '0.9rem' }}>
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
                  key={sess.id}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'flex-start',
                    paddingBottom: '12px',
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                  }}
                >
                  <MessageSquare size={16} color="var(--mist)" style={{ marginTop: '4px' }} />
                  <div>
                    <div style={{ fontSize: '0.9rem', marginBottom: '4px' }}>
                      {sess.summary}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        gap: '8px',
                        fontSize: '0.8rem',
                        color: 'var(--mist)',
                      }}
                    >
                      <span>{sess.timestamp}</span>
                      <span>•</span>
                      <span>{sess.duration}</span>
                      <span>•</span>
                      <span style={{ color: 'var(--ember)' }}>{sess.mood}</span>
                    </div>
                  </div>
                </div>
              ))}
              {sessions.length === 0 && (
                <div style={{ color: 'var(--mist)', fontSize: '0.9rem' }}>
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
