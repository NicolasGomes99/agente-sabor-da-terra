import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { RegistryNavigation } from '../components/RegistryNavigation'
import { getProducer } from '../registryApi'
import type { Producer } from '../types'

import './producer-detail.css'

type DetailState =
  | { status: 'loading' }
  | { status: 'not-found' }
  | { status: 'error' }
  | { status: 'ready'; producer: Producer }

function displayOptional(value: string | null): string {
  return value?.trim() || 'Não informado'
}

function ProducerDetails({ producerId }: { producerId: string }) {
  const { logout } = useAuth()
  const [state, setState] = useState<DetailState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    async function loadProducer() {
      try {
        const producer = await getProducer(producerId, controller.signal)
        if (!controller.signal.aborted) setState({ status: 'ready', producer })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        setState({ status: error instanceof ApiError && error.status === 404 ? 'not-found' : 'error' })
      }
    }

    void loadProducer()
    return () => controller.abort()
  }, [attempt, logout, producerId])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  if (state.status === 'loading') return <p role="status">Carregando produtor…</p>
  if (state.status === 'not-found') return <p role="status">Produtor não encontrado.</p>
  if (state.status === 'error') {
    return (
      <>
        <p role="alert">Não foi possível carregar os dados do produtor.</p>
        <button className="producer-detail-retry" type="button" onClick={retry}>
          Tentar novamente
        </button>
      </>
    )
  }

  const { name, code, cpf, active, municipality, address, phone, email, products } = state.producer
  const fields = [
    ['Código', code],
    ['CPF', cpf],
    ['Situação', active ? 'Ativo' : 'Inativo'],
    ['Município', displayOptional(municipality)],
    ['Endereço', displayOptional(address)],
    ['Telefone', displayOptional(phone)],
    ['E-mail', displayOptional(email)],
  ]

  return (
    <>
      <h2>{name}</h2>
      <div className="producer-detail-sections">
        <section aria-labelledby="producer-registration-heading">
          <h3 id="producer-registration-heading">Dados cadastrais</h3>
          <dl>
            {fields.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section aria-labelledby="producer-products-heading">
          <h3 id="producer-products-heading">Produtos associados</h3>
          {products.length > 0 ? (
            <ul>
              {products.map(({ id, name: productName }) => <li key={id}>{productName}</li>)}
            </ul>
          ) : (
            <p>Nenhum produto associado.</p>
          )}
        </section>
      </div>
    </>
  )
}

export function ProducerDetailPage() {
  const { producerId } = useParams<'producerId'>()
  const { search } = useLocation()

  return (
    <AppShell>
      <div className="producer-detail-page">
        <p className="producer-detail-section-label">Cadastros</p>
        <h1>Detalhe do produtor</h1>
        <RegistryNavigation />
        <Link className="producer-detail-back" to={{ pathname: '/registry/producers', search }}>
          Voltar para produtores
        </Link>
        {producerId && <ProducerDetails key={producerId} producerId={producerId} />}
      </div>
    </AppShell>
  )
}
