// First-run checklist. Reflects live setup state from /api/onboarding and checks
// itself off as the user completes each step. Hidden once fully onboarded.

function Step({ status, title, children }) {
  const icon = status === 'done' ? '✓' : status === 'warn' ? '!' : '○'
  return (
    <li className={`ob-step ${status}`}>
      <span className="ob-icon" aria-hidden>{icon}</span>
      <div className="ob-body">
        <div className="ob-title">{title}</div>
        {children && <div className="ob-help">{children}</div>}
      </div>
    </li>
  )
}

function engineStep(o) {
  if (o.coach_provider === 'claude') {
    return o.claude_key_set
      ? { status: 'done', node: <>Claude API key is set.</> }
      : { status: 'warn', node: <>Add your Anthropic API key on the <strong>Settings</strong> screen.</> }
  }
  if (!o.ollama_reachable) {
    return {
      status: 'warn',
      node: <>Ollama isn’t running. Install it from <strong>ollama.com</strong> — it starts
        automatically after install — then reload this page.</>,
    }
  }
  if (!o.ollama_model_present) {
    return {
      status: 'warn',
      node: <>Ollama is running, but the model isn’t downloaded yet. In a terminal run{' '}
        <code>ollama pull {o.ollama_model}</code> (a one-time ~9&nbsp;GB download), then reload.</>,
    }
  }
  return { status: 'done', node: <>Ollama is running with <code>{o.ollama_model}</code> ready.</> }
}

export default function Onboarding({ data, onDismiss }) {
  if (!data) return null
  const eng = engineStep(data)
  const hasUser = !!data.chesscom_username
  const hasGames = data.games > 0
  const analyzed = data.engine_analyzed > 0
  const coached = data.coached > 0

  return (
    <div className="onboarding card">
      <button className="ob-dismiss" onClick={onDismiss} title="Hide this">✕</button>
      <h2 className="ob-head">♞ Welcome to ChessCoach</h2>
      <p className="ob-sub">
        Free, local positional coaching for your own games — Stockfish for the engine,
        a local LLM for the strategic <em>why</em>. A quick one-time setup:
      </p>
      <ol className="ob-list">
        <Step status={eng.status} title="1 · Coaching engine ready">{eng.node}</Step>
        <Step status={hasUser ? 'done' : 'todo'} title="2 · Connect your chess.com account">
          {hasUser
            ? <>Importing games for <strong>{data.chesscom_username}</strong>.</>
            : <>Enter your chess.com username in the bar below and import.</>}
        </Step>
        <Step status={hasGames ? 'done' : 'todo'} title="3 · Import your games">
          {hasGames
            ? <>{data.games} game{data.games === 1 ? '' : 's'} imported.</>
            : <>Use the import bar below to pull your recent games (free chess.com API).</>}
        </Step>
        <Step status={analyzed ? 'done' : 'todo'} title="4 · Analyze a game">
          {analyzed
            ? <>{data.engine_analyzed} game{data.engine_analyzed === 1 ? '' : 's'} analyzed.</>
            : <>Open any game and click <strong>Run engine analysis</strong> for evals + move grades.</>}
        </Step>
        <Step status={coached ? 'done' : 'todo'} title="5 · Get coaching">
          {coached
            ? <>{data.coached} game{data.coached === 1 ? '' : 's'} coached — you’re all set!</>
            : <>In an analyzed game, click <strong>Get coaching</strong> for the positional report.</>}
        </Step>
      </ol>
    </div>
  )
}
