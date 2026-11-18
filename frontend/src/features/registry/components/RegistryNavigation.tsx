import { NavLink } from 'react-router-dom'

import './registry-navigation.css'

export function RegistryNavigation() {
  return (
    <nav className="registry-navigation" aria-label="Consultas de Cadastros">
      <NavLink to="/registry/products">Produtos</NavLink>
      <NavLink to="/registry/producers">Produtores</NavLink>
    </nav>
  )
}
