import React from 'react'
import ReactDOM from 'react-dom/client'
import ProductsApp from './ProductsApp.jsx'
import './styles/tokens.css'
import './styles/site.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ProductsApp />
  </React.StrictMode>,
)
