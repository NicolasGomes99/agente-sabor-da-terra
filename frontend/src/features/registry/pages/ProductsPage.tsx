import { useEffect, useState } from 'react'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { listProducts } from '../registryApi'
import type { Product } from '../types'

import './products.css'

type CatalogState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; products: Product[] }

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase().normalize('NFD').replace(/\p{M}/gu, '')
}

export function ProductsPage() {
  const { logout } = useAuth()
  const [state, setState] = useState<CatalogState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [search, setSearch] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    async function loadProducts() {
      try {
        const products = await listProducts(controller.signal)
        if (!controller.signal.aborted) setState({ status: 'ready', products })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        setState({ status: 'error' })
      }
    }

    void loadProducts()
    return () => controller.abort()
  }, [attempt, logout])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  const query = normalizeSearch(search)
  const visibleProducts = state.status === 'ready'
    ? state.products.filter((product) => normalizeSearch(product.name).includes(query))
    : []

  return (
    <AppShell>
      <div className="products-page">
        <p className="products-section-label">Cadastros</p>
        <h1>Produtos</h1>

        {state.status === 'loading' && <p role="status">Carregando produtos…</p>}
        {state.status === 'error' && (
          <>
            <p role="alert">Não foi possível carregar os produtos.</p>
            <button type="button" onClick={retry}>Tentar novamente</button>
          </>
        )}
        {state.status === 'ready' && state.products.length === 0 && (
          <p role="status">Nenhum produto cadastrado.</p>
        )}
        {state.status === 'ready' && state.products.length > 0 && (
          <>
            <div className="products-search">
              <div>
                <label htmlFor="product-search">Buscar por nome</label>
                <input
                  id="product-search"
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <button type="button" onClick={() => setSearch('')} disabled={search === ''}>
                Limpar busca
              </button>
            </div>
            {visibleProducts.length === 0 ? (
              <p role="status">Nenhum produto corresponde à busca.</p>
            ) : (
              <ul className="products-list">
                {visibleProducts.map((product) => <li key={product.id}>{product.name}</li>)}
              </ul>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
