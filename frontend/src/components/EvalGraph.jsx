import { Area, AreaChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const CLAMP = 8

function evalLabel(move) {
  if (!move) return 'Start'
  if (move.eval_mate != null) return `M${Math.abs(move.eval_mate)}`
  const v = move.eval_cp / 100
  return (v > 0 ? '+' : '') + v.toFixed(1)
}

export default function EvalGraph({ moves, currentPly, currentMove, onSelect }) {
  const data = [{ ply: 0, eval: 0.2 }].concat(
    moves.map((m) => ({
      ply: m.ply,
      eval: Math.max(-CLAMP, Math.min(CLAMP,
        m.eval_mate != null ? (m.eval_mate > 0 ? CLAMP : -CLAMP) : m.eval_cp / 100)),
      san: m.san,
    }))
  )
  const current = data.find((d) => d.ply === currentPly)

  return (
    <div className="card" style={{ padding: '10px 4px 6px' }}>
      <div className="eval-readout">
        {evalLabel(currentMove)}
        {currentMove && (
          <span className="eval-move-label">
            {' '}after {Math.ceil(currentPly / 2)}{currentPly % 2 ? '.' : '…'} {currentMove.san}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <AreaChart data={data} onClick={(e) => { if (e?.activeLabel != null) onSelect(Number(e.activeLabel)) }}>
          <defs>
            <linearGradient id="evalFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e8e8e8" stopOpacity={0.9} />
              <stop offset="50%" stopColor="#888" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#222" stopOpacity={0.9} />
            </linearGradient>
          </defs>
          <XAxis dataKey="ply" hide />
          <YAxis domain={[-CLAMP, CLAMP]} hide />
          <ReferenceLine y={0} stroke="#555" />
          <Tooltip
            contentStyle={{ background: '#1e2128', border: '1px solid #333845', fontSize: 12 }}
            formatter={(v) => [(v > 0 ? '+' : '') + v.toFixed(1), 'eval']}
            labelFormatter={(ply) => {
              const d = data.find((x) => x.ply === ply)
              return d?.san ? `${Math.ceil(ply / 2)}${ply % 2 ? '.' : '…'} ${d.san}` : 'Start'
            }}
          />
          <Area type="monotone" dataKey="eval" stroke="#9aa2b1" fill="url(#evalFill)" isAnimationActive={false} />
          {current && <ReferenceDot x={current.ply} y={current.eval} r={4} fill="#6ea8fe" stroke="none" />}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
