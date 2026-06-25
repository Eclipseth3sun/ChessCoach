const BADGES = {
  brilliant: '‼',
  great: '!',
  best: '★',
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
}

function Move({ move, currentPly, rushedPlies, onSelect }) {
  if (!move) return <span />
  const badge = BADGES[move.classification]
  const hasTime = badge && move.time_spent != null
  // "rushed" is decided server-side (fast for the position + still competitive),
  // so a correct fast endgame move is never flagged.
  const rushed = rushedPlies?.has(move.ply)
  return (
    <span
      className={`move ${move.ply === currentPly ? 'current' : ''}`}
      onClick={() => onSelect(move.ply)}
      title={move.time_spent != null ? `${Math.round(move.time_spent)}s spent` : undefined}
    >
      {move.san}
      {badge && <span className={`badge ${move.classification}`}>{badge}</span>}
      {hasTime && <span className={`mtime ${rushed ? 'rushed' : ''}`}>{Math.round(move.time_spent)}s</span>}
    </span>
  )
}

export default function MoveList({ moves, currentPly, rushedPlies, onSelect }) {
  const rows = []
  for (let i = 0; i < moves.length; i += 2) {
    rows.push({ num: i / 2 + 1, white: moves[i], black: moves[i + 1] })
  }
  return (
    <div className="moves">
      {rows.map((r) => (
        <FragmentRow key={r.num} row={r} currentPly={currentPly} rushedPlies={rushedPlies} onSelect={onSelect} />
      ))}
    </div>
  )
}

function FragmentRow({ row, currentPly, rushedPlies, onSelect }) {
  return (
    <>
      <span className="num">{row.num}.</span>
      <Move move={row.white} currentPly={currentPly} rushedPlies={rushedPlies} onSelect={onSelect} />
      <Move move={row.black} currentPly={currentPly} rushedPlies={rushedPlies} onSelect={onSelect} />
    </>
  )
}
