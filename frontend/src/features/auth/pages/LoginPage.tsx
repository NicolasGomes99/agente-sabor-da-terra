import { LoginForm } from '../components/LoginForm'
import './login.css'

interface LoginPageProps {
  onAuthenticated?: () => void
}

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <p className="login-brand">Sabor da Terra</p>
        <h1 id="login-title">Acesso à cooperativa</h1>
        <p className="login-description">
          Entre para acompanhar pedidos e conversar com o assistente.
        </p>
        <LoginForm onSuccess={onAuthenticated} />
      </section>
    </main>
  )
}
