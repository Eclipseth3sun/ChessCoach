import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { applyStoredTheme } from './components/ThemePicker.jsx'

applyStoredTheme() // set data-theme before first paint to avoid a flash

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
