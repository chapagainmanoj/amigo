import { CheckSquare } from 'lucide-react'

export default function ModeChips() {
  return (
    <div className="mode-chips-bar" aria-label="Amigo modes">
      <span className="mode-chips-label">Active mode</span>
      <div className="mode-chips-row">
        <div className="mode-chip mode-chip--active" aria-current="true" title="Daily mode">
          <CheckSquare size={14} strokeWidth={1.8} />
          <span>Daily</span>
        </div>
      </div>
    </div>
  )
}
