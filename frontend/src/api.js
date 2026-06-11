async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail } catch { /* keep statusText */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  settings: () => request('/api/settings'),
  saveSettings: (s) => request('/api/settings', { method: 'PUT', body: JSON.stringify(s) }),
  importGames: (username, months) =>
    request('/api/import', { method: 'POST', body: JSON.stringify({ username, months }) }),
  games: () => request('/api/games'),
  onboarding: () => request('/api/onboarding'),
  game: (id) => request(`/api/games/${id}`),
  analyze: (id) => request(`/api/games/${id}/analyze`, { method: 'POST' }),
  analyzeStatus: (id) => request(`/api/games/${id}/analyze/status`),
  coach: (id) => request(`/api/games/${id}/coach`, { method: 'POST' }),
  coachStatus: (id) => request(`/api/games/${id}/coach/status`),
  bestLine: (id, ply) => request(`/api/games/${id}/bestline/${ply}`),
}
