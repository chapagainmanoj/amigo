import React from 'react'
import ReactDOM from 'react-dom/client'
import ContactApp from './ContactApp.jsx'
import './styles/tokens.css'
import './styles/site.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ContactApp />
  </React.StrictMode>,
)
