import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import Onboarding from './Onboarding.jsx'
import InfoTip from './InfoTip.jsx'

function outcome(game) {
  if (!game.user_color || game.result === '1/2-1/2') return 'draw'
  return (game.user_color === 'white') === (game.result === '1-0') ? 'win' : 'loss'
}

function resultLabel(game) {
  const o = outcome(game)
  return o === 'draw' ? '½–½' : o === 'win' ? 'Win' : 'Loss'
}

export default function GameList({ onOpen }) {
  const [games, setGames] = useState([])
  const [username, setUsername] = useState('')
  const [months, setMonths] = useState(3)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [ob, setOb] = useState(null)
  const [dismissed, setDismissed] = useState(false)
  const [loading, setLoading] = useState(true)

  const refresh = () => api.games().then(setGames)
    .catch((e) => setStatus(e.message)).finally(() => setLoading(false))
  const refreshOb = () => api.onboarding().then(setOb).catch(() => {})

  useEffect(() => {
    refresh()
    refreshOb()
    api.settings().then((s) => setUsername(s.chesscom_username || '')).catch(() => {})
  }, [])

  const doImport = async () => {
    setBusy(true)
    setStatus('Importing from chess.com…')
    try {
      await api.saveSettings({ chesscom_username: username })
      const r = await api.importGames(username, months)
      setStatus(`Imported ${r.imported} new games (${r.skipped} already known) from ${r.archives} month(s).`)
      refresh()
      refreshOb()
    } catch (e) {
      setStatus(`Import failed: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const stats = useMemo(() => {
    const s = { total: games.length, wins: 0, losses: 0, draws: 0, analyzed: 0, coached: 0 }
    for (const g of games) {
      if (g.engine_analyzed) s.analyzed++
      if (g.coached) s.coached++
      const o = outcome(g)
      if (o === 'win') s.wins++; else if (o === 'loss') s.losses++; else s.draws++
    }
    return s
  }, [games])

  const setupOk = ob && (ob.coach_provider === 'claude'
    ? ob.claude_key_set
    : (ob.ollama_reachable && ob.ollama_model_present))
  const onboarded = ob && setupOk && ob.games > 0 && ob.coached > 0
  // ?welcome=1 forces the card open (for review/screenshots even when onboarded)
  const forceWelcome = typeof window !== 'undefined'
    && new URLSearchParams(window.location.search).has('welcome')
  const showOnboarding = ob && (forceWelcome || (!onboarded && !dismissed))

  return (
    <div>
      {showOnboarding && <Onboarding data={ob} onDismiss={() => setDismissed(true)} />}

      <div className="page-head">
        <h2>Your games</h2>
        {stats.total > 0 && (
          <div className="stats-strip">
            <div className="stat-card">
              <div className="stat-num">{stats.total}</div>
              <div className="stat-label">Games</div>
            </div>
            <div className="stat-card">
              <div className="stat-num">
                <span className="wl-w">{stats.wins}</span>
                <span className="wl-sep">–</span>
                <span className="wl-l">{stats.losses}</span>
                <span className="wl-sep">–</span>
                <span className="wl-d">{stats.draws}</span>
              </div>
              <div className="stat-label">W·L·D</div>
            </div>
            <div className="stat-card">
              <div className="stat-num">{stats.analyzed}</div>
              <div className="stat-label">Analyzed</div>
            </div>
            <div className="stat-card">
              <div className="stat-num">{stats.coached}</div>
              <div className="stat-label">Coached</div>
            </div>
          </div>
        )}
      </div>

      <div className="import-bar">
        <input
          placeholder="chess.com username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <select
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          title="How far back to pull from your chess.com archive"
        >
          <option value={1}>last month</option>
          <option value={3}>last 3 months</option>
          <option value={6}>last 6 months</option>
          <option value={12}>last 12 months</option>
        </select>
        <button className="primary" onClick={doImport} disabled={busy || !username}>
          {busy ? 'Importing…' : 'Import games'}
        </button>
        <span className="status-line">{status}</span>
      </div>

      <table className="game-table">
        <thead>
          <tr>
            <th>Date</th><th>White</th><th>Black</th><th>Result</th>
            <th>Opening</th><th>Time</th>
            <th>
              Analysis{' '}
              <InfoTip side="left">
                <strong>—</strong> not analyzed yet · <strong>engine</strong> = Stockfish
                evals &amp; move grades done · <strong>coached</strong> = positional report ready.
              </InfoTip>
            </th>
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: 6 }).map((_, i) => (
            <tr key={`sk${i}`} className="sk-tr">
              <td colSpan={7}><div className="skeleton sk-row" /></td>
            </tr>
          ))}
          {!loading && games.map((g) => {
            const o = outcome(g)
            const youWhite = g.user_color === 'white'
            const youBlack = g.user_color === 'black'
            return (
              <tr key={g.id} className="row" onClick={() => onOpen(g.id)}>
                <td>{(g.played_at || '').slice(0, 10)}</td>
                <td className={youWhite ? 'you-name' : ''}>{g.white} {g.white_elo ? `(${g.white_elo})` : ''}</td>
                <td className={youBlack ? 'you-name' : ''}>{g.black} {g.black_elo ? `(${g.black_elo})` : ''}</td>
                <td><span className={`result-chip ${o}`}>{resultLabel(g)}</span></td>
                <td>{(g.opening || g.eco || '').slice(0, 40)}</td>
                <td>{g.time_control}</td>
                <td>
                  {g.coached ? <span className="pill done">coached</span>
                    : g.engine_analyzed ? <span className="pill done">engine</span>
                    : <span className="pill">—</span>}
                </td>
              </tr>
            )
          })}
          {!loading && games.length === 0 && (
            <tr><td colSpan={7} className="status-line">No games yet — import your chess.com archive above.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
