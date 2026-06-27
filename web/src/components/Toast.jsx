import { useState, useEffect } from 'react'

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
      backgroundColor: 'var(--ember)',
      color: 'var(--ink)',
      padding: '12px 24px',
      borderRadius: '8px',
      fontWeight: '600',
      boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      zIndex: 1000
    }}>
      {message}
    </div>
  )
}
