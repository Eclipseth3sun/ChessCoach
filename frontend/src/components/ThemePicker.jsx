import { useState } from 'react'

// Swatch preview colors mirror the palettes defined in index.css.
const THEMES = [
  { id: 'midnight', name: 'Midnight', bg: '#15171c', accent: '#6ea8fe' },
  { id: 'walnut', name: 'Walnut', bg: '#1b1613', accent: '#e0a96a' },
  { id: 'forest', name: 'Forest', bg: '#131815', accent: '#cdab57' },
  { id: 'royal', name: 'Royal', bg: '#15131f', accent: '#a78bfa' },
]

export function applyStoredTheme() {
  const saved = localStorage.getItem('cc-theme')
  if (saved) document.documentElement.dataset.theme = saved
}

export default function ThemePicker() {
  const [theme, setTheme] = useState(() => localStorage.getItem('cc-theme') || 'midnight')

  const apply = (id) => {
    setTheme(id)
    document.documentElement.dataset.theme = id
    localStorage.setItem('cc-theme', id)
  }

  return (
    <div className="theme-picker" title="Color theme">
      {THEMES.map((t) => (
        <button
          key={t.id}
          className={`swatch ${theme === t.id ? 'active' : ''}`}
          style={{ background: t.bg, color: t.accent }}
          onClick={() => apply(t.id)}
          title={`${t.name} theme`}
          aria-label={`${t.name} theme`}
          aria-pressed={theme === t.id}
        >
          <span className="swatch-dot" style={{ background: t.accent }} />
        </button>
      ))}
    </div>
  )
}
