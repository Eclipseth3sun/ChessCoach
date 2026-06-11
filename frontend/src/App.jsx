import { useState } from 'react'
import GameList from './components/GameList.jsx'
import GameView from './components/GameView.jsx'
import Settings from './components/Settings.jsx'
import ThemePicker from './components/ThemePicker.jsx'

export default function App() {
  const [view, setView] = useState({ name: 'list' })

  return (
    <>
      <div className="topbar">
        <div className="brand" onClick={() => setView({ name: 'list' })} title="Home">
          <span className="brand-mark">♞</span>
          <span className="brand-name">ChessCoach</span>
          <span className="brand-tag">positional coaching</span>
        </div>
        <div className="spacer" />
        {view.name !== 'list' && (
          <button onClick={() => setView({ name: 'list' })}>← Games</button>
        )}
        <ThemePicker />
        <button onClick={() => setView({ name: 'settings' })}>Settings</button>
      </div>
      <div className="page">
        {view.name === 'list' && (
          <GameList onOpen={(id) => setView({ name: 'game', id })} />
        )}
        {view.name === 'game' && <GameView gameId={view.id} />}
        {view.name === 'settings' && <Settings />}
      </div>
    </>
  )
}
