const BADGES = {
  brilliant: '‼',
  great: '!',
  best: '★',
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
}

function Move({ move, currentPly, onSelect }) {
  if (!move) return <span />
  const badge = BADGES[move.classification]
  return (
    <span
      className={`move ${move.ply === currentPly ? 'current' : ''}`}
      onClick={() => onSelect(move.ply)}
    >
      {move.san}
      {badge && <span className={`badge ${move.classification}`}>{badge}</span>}
    </span>
  )
}

export default function MoveList({ moves, currentPly, onSelect }) {
  const rows = []
  for (let i = 0; i < moves.length; i += 2) {
    rows.push({ num: i / 2 + 1, white: moves[i], black: moves[i + 1] })
  }
  return (
    <div className="moves">
      {rows.map((r) => (
        <FragmentRow key={r.num} row={r} currentPly={currentPly} onSelect={onSelect} />
      ))}
    </div>
  )
}

function FragmentRow({ row, currentPly, onSelect }) {
  return (
    <>
      <span className="num">{row.num}.</span>
      <Move move={row.white} currentPly={currentPly} onSelect={onSelect} />
      <Move move={row.black} currentPly={currentPly} onSelect={onSelect} />
    </>
  )
}
