import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Circle, Clock, MessageSquare, Trash2, Plus } from 'lucide-react'
import { supabase } from '../supabase'
import { timeOfDayGreeting } from '../mockData'
import Toast from './Toast'
import ModeChips from './ModeChips'

export default function DashboardView({ pairedUser }) {
  const [tasks, setTasks] = useState([])
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
      .eq('created_date', todayStr)
      .order('created_at', { ascending: false })
    if (!error && data) {
      setTasks(data)
    }
  }, [getLocalDateString])

  const fetchReminders = useCallback(async () => {
    const { data, error } = await supabase
      .from('reminders')
      .select('*, tasks(title, category)')
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
    fetchReminders()
    fetchSessions()

    // Realtime channel subscriptions
    const tasksChannel = supabase
      .channel('tasks-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' }, () => {
        fetchTasks()
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
  }, [fetchReminders, fetchSessions, fetchTasks])

  const handleToggleTask = async (id, currentStatus) => {
    const nextStatus = currentStatus === 'done' ? 'pending' : 'done'
    const actualCompletion = nextStatus === 'done' ? new Date().toISOString() : null

    const { error } = await supabase
      .from('tasks')
      .update({ status: nextStatus, actual_completion: actualCompletion })
      .eq('task_id', id)

    if (error) {
      setToastMsg('Failed to update task')
    } else {
      setToastMsg(nextStatus === 'done' ? 'Task completed' : 'Task updated')
    }
  }

  const handleDeleteTask = async (id) => {
    const { error } = await supabase.from('tasks').delete().eq('task_id', id)

    if (error) {
      setToastMsg('Failed to delete task')
    } else {
      setToastMsg('Task removed')
    }
  }

  const handleAddTask = async (e) => {
    e.preventDefault()
    if (!newTaskTitle.trim()) return

    const todayStr = getLocalDateString()
    const { error } = await supabase.from('tasks').insert({
      title: newTaskTitle,
      status: 'pending',
      category: 'other',
      user_id: pairedUser.user_id,
      created_date: todayStr,
    })

    if (error) {
      setToastMsg('Failed to add task')
    } else {
      setNewTaskTitle('')
      setToastMsg('Task added')
    }
  }

  const handleSnooze = async (id, scheduledTime) => {
    const current = new Date(scheduledTime)
    const nextTime = new Date(current.getTime() + 15 * 60 * 1000).toISOString()

    const { data: remData } = await supabase
      .from('reminders')
      .select('snooze_count')
      .eq('reminder_id', id)
      .single()

    const currentCount = remData?.snooze_count || 0

    const { error } = await supabase
      .from('reminders')
      .update({
        scheduled_time: nextTime,
        status: 'pending',
        snooze_count: currentCount + 1,
      })
      .eq('reminder_id', id)

    if (error) {
      setToastMsg('Failed to snooze reminder')
    } else {
      setToastMsg('Snoozed for 15m')
    }
  }

  const doneCount = tasks.filter((t) => t.status === 'done').length
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
                    opacity: task.status === 'done' ? 0.6 : 1,
                    transition: 'opacity 0.2s ease',
                  }}
                >
                  <button
                    onClick={() => handleToggleTask(task.task_id, task.status)}
                    style={{
                      background: 'transparent',
                      color: task.status === 'done' ? 'var(--ember)' : 'var(--mist)',
                      marginRight: '12px',
                      flexShrink: 0,
                    }}
                  >
                    {task.status === 'done' ? (
                      <CheckCircle2 size={24} className="animate-pop" />
                    ) : (
                      <Circle size={24} />
                    )}
                  </button>
                  <span
                    style={{
                      flex: 1,
                      textDecoration: task.status === 'done' ? 'line-through' : 'none',
                      color: task.status === 'done' ? 'var(--mist)' : 'var(--paper)',
                    }}
                  >
                    {task.title}
                  </span>
                  <button
                    onClick={() => handleDeleteTask(task.task_id)}
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
                    onClick={() => handleSnooze(rem.id, rem.scheduled_time)}
                    className="btn-secondary"
                    style={{ width: '100%', fontSize: '0.85rem' }}
                  >
                    Snooze 15m
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
