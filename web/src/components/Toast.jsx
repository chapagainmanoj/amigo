import { useEffect } from 'react'

export default function Toast({ message, onClose }) {
  useEffect(() => {
    if (message) {
      const timer = setTimeout(onClose, 3000)
      return () => clearTimeout(timer)
    }
  }, [message, onClose])

  if (!message) return null

  return (
    <div className="animate-slide-in" style={{
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      backgroundColor: 'var(--oat)',
      color: 'var(--oat)',
      padding: '12px 24px',
      borderRadius: '8px',
      fontWeight: '600',
      border: '1px solid var(--rule)',
      zIndex: 1000
    }}>
      {message}
    </div>
  )
}
