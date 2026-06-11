import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Settings() {
  const [cfg, setCfg] = useState(null)
  const [apiKey, setApiKey] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => { api.settings().then(setCfg).catch((e) => setStatus(e.message)) }, [])

  if (!cfg) return <div className="status-line">{status || 'Loading…'}</div>

  const isOllama = cfg.coach_provider !== 'claude'

  const save = async () => {
    setStatus('Saving…')
    try {
      const updates = {
        chesscom_username: cfg.chesscom_username,
        coach_provider: cfg.coach_provider,
        ollama_url: cfg.ollama_url,
        ollama_model: cfg.ollama_model,
        claude_model: cfg.claude_model,
        engine_movetime_ms: Number(cfg.engine_movetime_ms),
        engine_threads: Number(cfg.engine_threads),
      }
      if (apiKey) updates.anthropic_api_key = apiKey
      const saved = await api.saveSettings(updates)
      setCfg(saved)
      setApiKey('')
      setStatus('Saved.')
    } catch (e) {
      setStatus(`Save failed: ${e.message}`)
    }
  }

  return (
    <div className="settings-form">
      <h2>Settings</h2>

      <label>
        chess.com username
        <input
          value={cfg.chesscom_username || ''}
          onChange={(e) => setCfg({ ...cfg, chesscom_username: e.target.value })}
        />
      </label>

      <label>
        Coach provider
        <select
          value={cfg.coach_provider || 'ollama'}
          onChange={(e) => setCfg({ ...cfg, coach_provider: e.target.value })}
        >
          <option value="ollama">Ollama — free local LLM (recommended)</option>
          <option value="claude">Claude API — best quality (costs per game)</option>
        </select>
      </label>

      {isOllama ? (
        <>
          <div className="card" style={{ padding: '10px 14px', fontSize: 13, lineHeight: 1.6 }}>
            <strong>Ollama setup (one time):</strong>
            <ol style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              <li>Install from <strong>ollama.com</strong></li>
              <li>Open a terminal and run: <code>ollama pull qwen2.5:14b</code></li>
              <li>Ollama runs automatically in the background after install.</li>
            </ol>
          </div>
          <label>
            Ollama URL
            <input
              value={cfg.ollama_url || 'http://localhost:11434'}
              onChange={(e) => setCfg({ ...cfg, ollama_url: e.target.value })}
            />
          </label>
          <label>
            Model
            <input
              value={cfg.ollama_model || 'qwen2.5:14b'}
              onChange={(e) => setCfg({ ...cfg, ollama_model: e.target.value })}
              placeholder="qwen2.5:14b"
            />
            <span className="status-line">
              qwen2.5:14b recommended (best grounding) · also works: llama3.1:8b, gemma2:9b, mistral
            </span>
          </label>
        </>
      ) : (
        <>
          <label>
            Anthropic API key {cfg.anthropic_api_key ? '(currently set)' : '(not set)'}
            <input
              type="password"
              placeholder={cfg.anthropic_api_key ? '•••••••• (leave blank to keep)' : 'sk-ant-…'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
          <label>
            Claude model
            <select
              value={cfg.claude_model}
              onChange={(e) => setCfg({ ...cfg, claude_model: e.target.value })}
            >
              <option value="claude-sonnet-4-6">Sonnet 4.6 (~3¢/game)</option>
              <option value="claude-haiku-4-5-20251001">Haiku 4.5 (~0.5¢/game)</option>
              <option value="claude-opus-4-8">Opus 4.8 (~15¢/game)</option>
            </select>
          </label>
        </>
      )}

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '4px 0' }} />

      <label>
        Engine time per move (ms) — higher = more accurate, slower
        <input
          type="number" min="50" max="2000" step="50"
          value={cfg.engine_movetime_ms}
          onChange={(e) => setCfg({ ...cfg, engine_movetime_ms: e.target.value })}
        />
      </label>
      <label>
        Engine threads
        <input
          type="number" min="1" max="16"
          value={cfg.engine_threads}
          onChange={(e) => setCfg({ ...cfg, engine_threads: e.target.value })}
        />
      </label>

      <div>
        <button className="primary" onClick={save}>Save</button>
        <span className="status-line" style={{ marginLeft: 10 }}>{status}</span>
      </div>
    </div>
  )
}
