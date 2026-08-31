let idCounter = 100
export const nextId = () => `mock_${idCounter++}`

export const mockTasks = [
  { id: nextId(), title: 'Review PR for the new caching layer', status: 'pending', category: 'work' },
  { id: nextId(), title: 'Drink water', status: 'completed', category: 'health' },
  { id: nextId(), title: 'Reply to Sarah about weekend plans', status: 'pending', category: 'personal' },
]

export const mockReminders = [
  { id: nextId(), label: 'Dentist appointment', time: 'Tomorrow, 10:00 AM' },
  { id: nextId(), label: 'Call mom', time: 'Today, 6:00 PM' },
]

export const mockSessions = [
  { id: nextId(), timestamp: '2 hours ago', duration: '14m', summary: 'Morning planning & task triage', mood: 'Focused' },
  { id: nextId(), timestamp: 'Yesterday', duration: '5m', summary: 'Quick check-in', mood: 'Casual' },
]

export function timeOfDayGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) {
    return {
      headline: 'Good morning',
      subtext: 'Ready to tackle the day?',
      gradient: 'linear-gradient(135deg, rgba(255,138,91,0.2) 0%, rgba(29,24,40,0) 100%)'
    }
  } else if (hour < 18) {
    return {
      headline: 'Good afternoon',
      subtext: 'Keeping the momentum going.',
      gradient: 'linear-gradient(135deg, rgba(243,194,106,0.2) 0%, rgba(29,24,40,0) 100%)'
    }
  } else {
    return {
      headline: 'Good evening',
      subtext: 'Time to wind down soon.',
      gradient: 'linear-gradient(135deg, rgba(183,178,201,0.2) 0%, rgba(29,24,40,0) 100%)'
    }
  }
}
