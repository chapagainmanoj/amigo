import { CheckSquare, Sparkles, Flame, Heart } from 'lucide-react'

const MODES = [
  { id: 'daily', label: 'Daily', Icon: CheckSquare, available: true },
  { id: 'recommender', label: 'Recommender', Icon: Sparkles, available: false },
  { id: 'coach', label: 'Coach', Icon: Flame, available: false },
  { id: 'reflect', label: 'Reflect', Icon: Heart, available: false },
]

export default function ModeChips({ activeMode, onModeChange }) {
  return (
    <div className="mode-chips-bar" aria-label="Amigo modes">
      <span className="mode-chips-label">Active mode</span>
      <div className="mode-chips-row">
        {MODES.map(({ id, label, Icon, available }) => (
          <button
            key={id}
            type="button"
            className={[
              'mode-chip',
              activeMode === id ? 'mode-chip--active' : '',
              !available ? 'mode-chip--soon' : '',
            ].join(' ').trim()}
            onClick={() => onModeChange(id)}
            aria-pressed={activeMode === id}
            aria-disabled={!available}
            title={!available ? `${label} mode is coming soon (click to preview)` : `${label} mode`}
          >
            <Icon size={14} strokeWidth={1.8} />
            <span>{label}</span>
            {!available && <span className="mode-chip-soon-tag">soon</span>}
          </button>
        ))}
      </div>
    </div>
  )
}
