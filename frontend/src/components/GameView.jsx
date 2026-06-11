import { useCallback, useEffect, useRef, useState } from 'react'
import { Chess } from 'chess.js'
import { Chessboard } from 'react-chessboard'
import { api } from '../api.js'
import EvalGraph from './EvalGraph.jsx'
import MoveList from './MoveList.jsx'
import CoachPanel from './CoachPanel.jsx'
import InfoTip from './InfoTip.jsx'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

// chess.com-style move-quality glyphs shown in the corner of the move's to-square
const MOVE_GLYPH = {
  brilliant: '‼',
  great: '!',
  best: '★',
  good: '✓',
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
}

export default function GameView({ gameId }) {
  const [game, setGame] = useState(null)
  const [ply, setPly] = useState(0)
  const [engineStatus, setEngineStatus] = useState(null)
  const [coachBusy, setCoachBusy] = useState(false)
  const [coachProgress, setCoachProgress] = useState(null)
  const [error, setError] = useState('')
  // variation: null | { fens, sans, step } — best-line walkthrough
  const [variation, setVariation] = useState(null)
  const [variationLoading, setVariationLoading] = useState(false)
  const pollRef = useRef(null)
  const coachPollRef = useRef(null)
  const boardRef = useRef(null)
  const [boardPx, setBoardPx] = useState(560)

  // measure the board container so the board fills it exactly (fixes row-gap rendering bug)
  useEffect(() => {
    if (!boardRef.current) return
    const ro = new ResizeObserver(([e]) => setBoardPx(e.contentRect.width))
    ro.observe(boardRef.current)
    return () => ro.disconnect()
  }, [])

  const load = useCallback(() => {
    api.game(gameId).then((g) => {
      setGame(g)
      setPly(g.moves.length ? g.moves.length : 0)
      setVariation(null)
    }).catch((e) => setError(e.message))
  }, [gameId])

  useEffect(() => { load() }, [load])
  useEffect(() => () => {
    clearInterval(pollRef.current)
    clearInterval(coachPollRef.current)
  }, [])

  const moves = game?.moves ?? []
  const maxPly = moves.length

  // keyboard navigation — arrow keys step through variation or game
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') { setVariation(null); return }
      if (variation) {
        if (e.key === 'ArrowRight')
          setVariation((v) => v.step < v.sans.length ? { ...v, step: v.step + 1 } : v)
        if (e.key === 'ArrowLeft')
          setVariation((v) => v.step > 0 ? { ...v, step: v.step - 1 } : v)
        return
      }
      if (e.key === 'ArrowLeft') setPly((p) => Math.max(0, p - 1))
      if (e.key === 'ArrowRight') setPly((p) => Math.min(maxPly, p + 1))
      if (e.key === 'Home') setPly(0)
      if (e.key === 'End') setPly(maxPly)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [maxPly, variation])

  // enter variation: fetch the full Stockfish PV for the position before `ply`,
  // then let the user step through it. Falls back to stored best_line on error.
  const enterVariation = useCallback(async ({ ply, baseFen, bestLineSans, playedUci, playedSan, momentType }) => {
    setVariationLoading(true)
    let fen = baseFen
    let sans = bestLineSans || []
    try {
      const result = await api.bestLine(gameId, ply)
      fen = result.fen
      sans = result.sans
    } catch {
      // keep stored line as fallback
    } finally {
      setVariationLoading(false)
    }
    const chess = new Chess(fen)
    const fens = [fen]
    const validSans = []
    for (const san of sans) {
      try { chess.move(san); fens.push(chess.fen()); validSans.push(san) }
      catch { break }
    }
    // Compute the position that actually occurred (the move the student played),
    // so step 0 can contrast "what you played" with "the best move".
    let playedFen = null
    if (playedUci) {
      try {
        const pc = new Chess(fen)
        pc.move({ from: playedUci.slice(0, 2), to: playedUci.slice(2, 4), promotion: playedUci.slice(4) || undefined })
        playedFen = pc.fen()
      } catch { /* ignore */ }
    }
    if (validSans.length > 0) {
      setVariation({
        fens, sans: validSans, step: 0,
        playedUci, playedSan, playedFen,
        momentType: momentType || 'negative',
      })
    }
  }, [gameId])

  const startAnalysis = async () => {
    setError('')
    try {
      await api.analyze(gameId)
      setEngineStatus({ status: 'running', done: 0, total: 1 })
      pollRef.current = setInterval(async () => {
        const s = await api.analyzeStatus(gameId).catch(() => null)
        if (!s) return
        setEngineStatus(s)
        if (s.status === 'done' || s.status === 'error') {
          clearInterval(pollRef.current)
          if (s.status === 'done') load()
          if (s.status === 'error') setError(s.error)
        }
      }, 1000)
    } catch (e) { setError(e.message) }
  }

  const startCoach = async () => {
    setError('')
    setCoachBusy(true)
    setCoachProgress({ done: 0, total: 1, label: 'Starting…' })
    try {
      await api.coach(gameId)
      coachPollRef.current = setInterval(async () => {
        const s = await api.coachStatus(gameId).catch(() => null)
        if (!s) return
        if (s.status === 'running') {
          setCoachProgress({ done: s.done, total: s.total, label: s.label })
        } else if (s.status === 'done' || s.status === 'error') {
          clearInterval(coachPollRef.current)
          setCoachBusy(false)
          setCoachProgress(null)
          if (s.status === 'done') load()
          if (s.status === 'error') setError(s.error)
        }
      }, 1200)
    } catch (e) {
      setError(e.message)
      setCoachBusy(false)
      setCoachProgress(null)
    }
  }

  if (!game) {
    if (error) return <div className="status-line error">{error}</div>
    return (
      <div className="game-layout">
        <div className="board-col">
          <div className="skeleton skeleton-board" />
          <div className="skeleton" style={{ height: 34, borderRadius: 6 }} />
        </div>
        <div className="side-col">
          <div className="skeleton" style={{ height: 92, borderRadius: 8 }} />
          <div className="skeleton" style={{ height: 220, borderRadius: 8 }} />
          <div className="skeleton" style={{ height: 160, borderRadius: 8 }} />
        </div>
      </div>
    )
  }

  // current FEN: variation takes priority over game position
  const gameFen = ply === 0 ? START_FEN : moves[ply - 1].fen_after
  const fen = variation ? variation.fens[variation.step] : gameFen

  const currentMove = ply > 0 ? moves[ply - 1] : null
  const nextMove = ply < maxPly ? moves[ply] : null
  const orientation = game.user_color === 'black' ? 'black' : 'white'
  const analyzed = game.engine_analyzed && moves.length > 0
  const engineRunning = engineStatus?.status === 'running'

  // arrows: in variation show the next move in the best line; otherwise show best move on errors
  const arrows = []
  if (variation) {
    if (variation.step < variation.sans.length) {
      const chess = new Chess(variation.fens[variation.step])
      try {
        const m = chess.move(variation.sans[variation.step])
        if (m) arrows.push({ startSquare: m.from, endSquare: m.to, color: '#4caf7d' })
      } catch { /* ignore */ }
    }
    // At the decision point (step 0) of a mistake, also show the move actually
    // played in red so the contrast with the best move (green) is explicit.
    if (variation.step === 0 && variation.momentType === 'negative' && variation.playedUci) {
      const from = variation.playedUci.slice(0, 2)
      const to = variation.playedUci.slice(2, 4)
      // only draw if it differs from the best move already shown in green
      if (!arrows.some((a) => a.startSquare === from && a.endSquare === to)) {
        arrows.push({ startSquare: from, endSquare: to, color: '#e05d5d' })
      }
    }
  } else if (nextMove?.best_uci &&
      ['inaccuracy', 'mistake', 'blunder'].includes(nextMove.classification)) {
    arrows.push({
      startSquare: nextMove.best_uci.slice(0, 2),
      endSquare: nextMove.best_uci.slice(2, 4),
      color: '#4caf7d',
    })
  }

  // move-quality badge on the to-square of the move just played (not in variation)
  let badge = null
  if (!variation && analyzed && currentMove?.uci && MOVE_GLYPH[currentMove.classification]) {
    const sq = boardPx / 8
    const f = currentMove.uci.charCodeAt(2) - 97   // 'a'..'h' -> 0..7
    const r = currentMove.uci.charCodeAt(3) - 49   // '1'..'8' -> 0..7
    const x = orientation === 'white' ? f * sq : (7 - f) * sq
    const y = orientation === 'white' ? (7 - r) * sq : r * sq
    const size = Math.max(15, sq * 0.42)
    badge = {
      glyph: MOVE_GLYPH[currentMove.classification],
      cls: currentMove.classification,
      left: x + sq * 0.80 - size / 2,
      top: y + sq * 0.20 - size / 2,
      size,
    }
  }

  return (
    <div className="game-layout">
      <div className="board-col">
        {variationLoading && (
          <div className="variation-banner">
            <span>Fetching deep line from Stockfish…</span>
          </div>
        )}
        {variation && !variationLoading && (
          <div className={`variation-banner ${variation.momentType === 'positive' ? 'positive' : ''}`}>
            <span>
              {variation.step === 0 && variation.momentType === 'negative' && variation.playedSan ? (
                <>
                  You played <span className="played-move">{variation.playedSan}</span> (red).
                  {' '}Best was <strong>{variation.sans[0]}</strong> (green) →
                </>
              ) : variation.momentType === 'positive' ? (
                <>Your move was best. Line continues: <strong>{variation.sans.join(' ')}</strong> · {variation.step}/{variation.sans.length}</>
              ) : (
                <>Best line: <strong>{variation.sans.join(' ')}</strong> · move {variation.step}/{variation.sans.length}</>
              )}
            </span>
            <button onClick={() => setVariation(null)}>✕ Exit</button>
          </div>
        )}
        <div ref={boardRef} style={{ width: '100%', aspectRatio: '1', position: 'relative' }}>
          <Chessboard
            options={{
              position: fen,
              boardOrientation: orientation,
              allowDragging: false,
              arrows,
              boardStyle: { width: boardPx + 'px', height: boardPx + 'px' },
              id: 'main-board',
            }}
          />
          {badge && (
            <div
              className={`move-badge ${badge.cls}`}
              style={{
                left: badge.left, top: badge.top,
                width: badge.size, height: badge.size,
                fontSize: badge.size * 0.5,
              }}
            >
              {badge.glyph}
            </div>
          )}
        </div>
        <div className="board-nav">
          {variation ? (
            <>
              <button onClick={() => setVariation((v) => ({ ...v, step: 0 }))}>⏮</button>
              <button onClick={() => setVariation((v) => v.step > 0 ? { ...v, step: v.step - 1 } : v)}>◀</button>
              <button onClick={() => setVariation((v) => v.step < v.sans.length ? { ...v, step: v.step + 1 } : v)}>▶</button>
              <button onClick={() => setVariation((v) => ({ ...v, step: v.sans.length }))}>⏭</button>
              <button onClick={() => setVariation(null)} style={{ marginLeft: 8 }}>✕ Exit</button>
            </>
          ) : (
            <>
              <button onClick={() => setPly(0)} title="First move (Home)">⏮</button>
              <button onClick={() => setPly(Math.max(0, ply - 1))} title="Previous move (←)">◀</button>
              <button onClick={() => setPly(Math.min(maxPly, ply + 1))} title="Next move (→)">▶</button>
              <button onClick={() => setPly(maxPly)} title="Last move (End)">⏭</button>
            </>
          )}
        </div>
        {analyzed && (
          <EvalGraph
            moves={moves}
            currentPly={ply}
            currentMove={currentMove}
            onSelect={(p) => { setVariation(null); setPly(p) }}
          />
        )}
      </div>

      <div className="side-col">
        <div className="card">
          <h3>
            {game.white} {game.white_elo ? `(${game.white_elo})` : ''} vs{' '}
            {game.black} {game.black_elo ? `(${game.black_elo})` : ''} · {game.result}
          </h3>
          <div className="status-line">
            {game.opening || game.eco} · {game.time_control} · {(game.played_at || '').slice(0, 10)}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
            <button
              className="primary" onClick={startAnalysis} disabled={engineRunning}
              title="Runs Stockfish on every move: the eval graph and move grades (★ best … ?? blunder). Takes ~10–30s. Required before coaching."
            >
              {engineRunning
                ? `Analyzing… ${engineStatus.done}/${engineStatus.total}`
                : analyzed ? 'Re-run engine' : 'Run engine analysis'}
            </button>
            <button
              className="primary" onClick={startCoach} disabled={!analyzed || coachBusy}
              title="Generates the positional report — one focused pass per key moment, then a game summary. Takes ~1–3 min."
            >
              {coachBusy ? 'Coach is thinking…' : game.coach ? 'Re-coach' : 'Get coaching'}
            </button>
            {!analyzed && (
              <InfoTip side="left">Start with <strong>Run engine analysis</strong> — coaching unlocks once a game is analyzed.</InfoTip>
            )}
          </div>
          {coachBusy && coachProgress && (
            <div className="coach-progress">
              <div className="coach-progress-label">
                {coachProgress.label} ({Math.min(coachProgress.done, coachProgress.total)}/{coachProgress.total})
              </div>
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{ width: `${Math.round(100 * coachProgress.done / Math.max(1, coachProgress.total))}%` }}
                />
              </div>
            </div>
          )}
          {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
        </div>

        {analyzed && (
          <div className="card">
            <h3>
              Moves{' '}
              <InfoTip>
                Move grades: <strong>‼ brilliant</strong> (sound sacrifice) ·
                {' '}<strong>! great</strong> (best under pressure) · <strong>★ best</strong> ·
                {' '}<strong>✓ good</strong> · <strong>?! inaccuracy</strong> ·
                {' '}<strong>? mistake</strong> · <strong>?? blunder</strong>.
              </InfoTip>
            </h3>
            <MoveList moves={moves} currentPly={ply} onSelect={(p) => { setVariation(null); setPly(p) }} />
          </div>
        )}

        <CoachPanel
          coach={game.coach}
          themes={game.themes}
          moves={moves}
          onJump={(p) => { setVariation(null); setPly(p) }}
          onVariation={enterVariation}
        />
      </div>
    </div>
  )
}
