import { NavLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../../features/auth/useAuth'

const navigationItems = [
  { label: 'Triagem', available: false },
  { label: 'Pedidos', available: false },
  { label: 'Agendamentos', available: false },
]

export function Sidebar() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout(): void {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <span className="brand-mark" aria-hidden="true">
          🌱
        </span>
        <span className="brand-name">Sabor da Terra</span>
      </div>

      <button className="new-chat-button" type="button" disabled>
        <span aria-hidden="true">+</span>
        Novo chat
      </button>

      <nav className="sidebar-navigation" aria-label="Navegação principal">
        <NavLink className="sidebar-nav-item" to="/chat">
          <span aria-hidden="true">◌</span>
          Chat
        </NavLink>
        <NavLink className="sidebar-nav-item" to="/documents">
          <span aria-hidden="true">▤</span>
          Documentos
        </NavLink>
        {navigationItems.map((item) => (
          <button
            className="sidebar-nav-item"
            key={item.label}
            type="button"
            disabled={!item.available}
          >
            <span aria-hidden="true">◇</span>
            {item.label}
          </button>
        ))}
        <NavLink className="sidebar-nav-item" to="/registry">
          <span aria-hidden="true">◇</span>
          Cadastros
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <div className="user-avatar" aria-hidden="true">
          U
        </div>
        <span className="sidebar-user">Usuário autenticado</span>
        <button
          className="logout-button"
          type="button"
          onClick={handleLogout}
          aria-label="Sair"
        >
          Sair
        </button>
      </div>
    </aside>
  )
}
