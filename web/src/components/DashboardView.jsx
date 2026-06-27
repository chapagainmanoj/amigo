import { useState, useEffect } from 'react'
import { CheckCircle2, Circle, Clock, MessageSquare, Trash2, Plus } from 'lucide-react'
import { mockTasks, mockReminders, mockSessions, timeOfDayGreeting, nextId } from '../mockData'
import Toast from './Toast'
import ModeChips from './ModeChips'

const HORIZON_SUBTEXTS = {
  daily: 'Keeping the momentum going.',
  recommender: 'Discover mode is coming soon. For now, keep steering the day from Daily.',
  coach: "Coach mode is coming soon. Today's tasks still get the front seat.",
  reflect: 'Reflect mode is coming soon. Daily planning stays active for now.',
}

export default function DashboardView({ activeMode, setActiveMode }) {
  const [tasks, setTasks] = useState(mockTasks)
  const [reminders, setReminders] = useState(mockReminders)
  const [toastMsg, setToastMsg] = useState(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [greeting, setGreeting] = useState(timeOfDayGreeting())

  useEffect(() => {
    // Update greeting if they keep it open across day boundaries
    const interval = setInterval(() => setGreeting(timeOfDayGreeting()), 60000)
    return () => clearInterval(interval)
  }, [])

  const handleToggleTask = (id) => {
    setTasks(tasks.map(t => {
      if (t.id === id) {
        const isCompleting = t.status !== 'done'
        if (isCompleting) setToastMsg('Task completed')
        return { ...t, status: isCompleting ? 'done' : 'pending' }
      }
      return t
    }))
  }

  const handleDeleteTask = (id) => {
    setTasks(tasks.filter(t => t.id !== id))
    setToastMsg('Task removed')
  }

  const handleAddTask = (e) => {
    e.preventDefault()
    if (!newTaskTitle.trim()) return
    setTasks([{ id: nextId(), title: newTaskTitle, status: 'pending', category: 'inbox' }, ...tasks])
    setNewTaskTitle('')
    setToastMsg('Task added')
  }

  const handleSnooze = (id) => {
    setToastMsg('Snoozed for 15m')
  }

  const doneCount = tasks.filter(t => t.status === 'done').length
  const totalCount = tasks.length

  return (
    <div className="animate-slide-in">
      {/* Daily Horizon Card (Glass) */}
      <div className="horizon-card">
        <div className="horizon-copy">
          <h1 className="horizon-greeting">
            {greeting.headline}
          </h1>
          <p className="horizon-subtext">
            {activeMode === 'daily' ? greeting.subtext : HORIZON_SUBTEXTS[activeMode]}
          </p>
          <div className="horizon-progress-pill">
            <CheckCircle2 size={16} color="var(--ember)" />
            <span>
              <strong>{doneCount}</strong> of {totalCount} done today
            </span>
          </div>
        </div>
      </div>

      <ModeChips activeMode={activeMode} onModeChange={setActiveMode} />

      <div className="dashboard-grid">
        
        {/* Main Column: Tasks */}
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 className="display-text" style={{ fontSize: '1.5rem' }}>Tasks</h2>
          </div>
          
          <div className="flat-card" style={{ padding: '24px' }}>
            <form onSubmit={handleAddTask} style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
              <input 
                type="text" 
                placeholder="Add a new task..." 
                value={newTaskTitle}
                onChange={(e) => setNewTaskTitle(e.target.value)}
                style={{ flex: 1, backgroundColor: 'rgba(255,255,255,0.03)' }}
              />
              <button type="submit" className="btn-primary" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 16px' }}>
                <Plus size={20} />
              </button>
            </form>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {tasks.map(task => (
                <div key={task.id} style={{ 
                  display: 'flex', alignItems: 'center', padding: '12px', 
                  background: 'rgba(255,255,255,0.02)', borderRadius: '8px',
                  opacity: task.status === 'done' ? 0.6 : 1,
                  transition: 'opacity 0.2s ease'
                }}>
                  <button 
                    onClick={() => handleToggleTask(task.id)} 
                    style={{ background: 'transparent', color: task.status === 'done' ? 'var(--ember)' : 'var(--mist)', marginRight: '12px', flexShrink: 0 }}
                  >
                    {task.status === 'done' ? <CheckCircle2 size={24} className="animate-pop" /> : <Circle size={24} />}
                  </button>
                  <span style={{ flex: 1, textDecoration: task.status === 'done' ? 'line-through' : 'none', color: task.status === 'done' ? 'var(--mist)' : 'var(--paper)' }}>
                    {task.title}
                  </span>
                  <button onClick={() => handleDeleteTask(task.id)} style={{ background: 'transparent', color: 'var(--mist)', padding: '4px' }}>
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              {tasks.length === 0 && <div style={{ color: 'var(--mist)', textAlign: 'center', padding: '24px 0' }}>No tasks pending.</div>}
            </div>
          </div>
        </section>

        {/* Sidebar Column: Reminders & Sessions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          <section>
            <h2 className="display-text" style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Active Reminders</h2>
            <div className="flat-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {reminders.map(rem => (
                <div key={rem.id} style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <Clock size={14} color="var(--gold)" />
                    <span style={{ fontSize: '0.85rem', color: 'var(--gold)' }}>{rem.time}</span>
                  </div>
                  <div style={{ fontSize: '0.95rem', marginBottom: '12px' }}>{rem.label}</div>
                  <button onClick={() => handleSnooze(rem.id)} className="btn-secondary" style={{ width: '100%', fontSize: '0.85rem' }}>
                    Snooze 15m
                  </button>
                </div>
              ))}
              {reminders.length === 0 && <div style={{ color: 'var(--mist)', fontSize: '0.9rem' }}>No active reminders.</div>}
            </div>
          </section>

          <section>
            <h2 className="display-text" style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Recent Sessions</h2>
            <div className="flat-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {mockSessions.map(sess => (
                <div key={sess.id} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', paddingBottom: '12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <MessageSquare size={16} color="var(--mist)" style={{ marginTop: '4px' }} />
                  <div>
                    <div style={{ fontSize: '0.9rem', marginBottom: '4px' }}>{sess.summary}</div>
                    <div style={{ display: 'flex', gap: '8px', fontSize: '0.8rem', color: 'var(--mist)' }}>
                      <span>{sess.timestamp}</span>
                      <span>•</span>
                      <span>{sess.duration}</span>
                      <span>•</span>
                      <span style={{ color: 'var(--ember)' }}>{sess.mood}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>
      <Toast message={toastMsg} onClose={() => setToastMsg(null)} />
    </div>
  )
}
