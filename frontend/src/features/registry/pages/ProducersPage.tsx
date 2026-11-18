import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AppShell } from '../../../components/layout/AppShell'
import { ApiError } from '../../../lib/api-client'
import { useAuth } from '../../auth/useAuth'
import { RegistryNavigation } from '../components/RegistryNavigation'
import { listProducers, listProducts } from '../registryApi'
import type { Producer, Product } from '../types'

import './producers.css'

type QueryResult<T> =
  | { status: 'error' }
  | { status: 'ready'; data: T }

type ProducerResult = {
  productId: string
  attempt: number
  result: QueryResult<{ producers: Producer[]; baseHasProducers: boolean }>
}

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase().normalize('NFD').replace(/\p{M}/gu, '')
}

export function ProducersPage() {
  const { logout } = useAuth()
  const [params, setParams] = useSearchParams()
  const search = params.get('q') ?? ''
  const productId = params.get('product_id') ?? ''
  const [catalog, setCatalog] = useState<QueryResult<Product[]> | null>(null)
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const [producerResult, setProducerResult] = useState<ProducerResult | null>(null)
  const [producerAttempt, setProducerAttempt] = useState(0)
  const baseHasProducers = useRef<boolean | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()

    async function loadCatalog() {
      try {
        const products = await listProducts(controller.signal)
        if (!controller.signal.aborted) setCatalog({ status: 'ready', data: products })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        setCatalog({ status: 'error' })
      }
    }

    void loadCatalog()
    return () => controller.abort()
  }, [catalogAttempt, logout])

  useEffect(() => {
    const controller = new AbortController()

    async function loadProducers() {
      try {
        const producers = await listProducers(productId || undefined, controller.signal)
        if (controller.signal.aborted) return

        let hasProducers = baseHasProducers.current
        if (!productId || producers.length > 0) {
          hasProducers = producers.length > 0
        } else if (hasProducers === undefined) {
          const allProducers = await listProducers(undefined, controller.signal)
          if (controller.signal.aborted) return
          hasProducers = allProducers.length > 0
        }

        baseHasProducers.current = hasProducers
        setProducerResult({
          productId,
          attempt: producerAttempt,
          result: { status: 'ready', data: { producers, baseHasProducers: hasProducers } },
        })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          logout()
          return
        }
        setProducerResult({ productId, attempt: producerAttempt, result: { status: 'error' } })
      }
    }

    void loadProducers()
    return () => controller.abort()
  }, [logout, productId, producerAttempt])

  function updateFilters(nextSearch: string, nextProduct: string) {
    const nextParams = new URLSearchParams(params)
    if (nextSearch) nextParams.set('q', nextSearch)
    else nextParams.delete('q')
    if (nextProduct) nextParams.set('product_id', nextProduct)
    else nextParams.delete('product_id')
    setParams(nextParams, { replace: true })
  }

  const result = producerResult?.productId === productId && producerResult.attempt === producerAttempt
    ? producerResult.result
    : null
  const query = normalizeSearch(search)
  const visibleProducers = result?.status === 'ready'
    ? result.data.producers.filter(({ name, code }) =>
      normalizeSearch(name).includes(query) || normalizeSearch(code).includes(query))
    : []
  const products = catalog?.status === 'ready' ? catalog.data : []

  return (
    <AppShell>
      <div className="producers-page">
        <p className="producers-section-label">Cadastros</p>
        <h1>Produtores</h1>
        <RegistryNavigation />

        <div className="producers-filters">
          <div>
            <label htmlFor="producer-search">Buscar por nome ou código</label>
            <input
              id="producer-search"
              type="search"
              value={search}
              onChange={(event) => updateFilters(event.target.value, productId)}
            />
          </div>
          <div>
            <label htmlFor="producer-product">Produto fornecido</label>
            <select
              id="producer-product"
              value={productId}
              disabled={catalog?.status !== 'ready'}
              onChange={(event) => updateFilters(search, event.target.value)}
            >
              <option value="">Todos os produtos</option>
              {productId && !products.some(({ id }) => id === productId) && (
                <option value={productId}>Produto selecionado</option>
              )}
              {products.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
            </select>
          </div>
          <button
            type="button"
            onClick={() => updateFilters('', '')}
            disabled={!search && !productId}
          >
            Limpar busca e filtro
          </button>
        </div>

        {catalog === null && <p role="status">Carregando opções de produtos…</p>}
        {catalog?.status === 'error' && (
          <>
            <p role="alert">Não foi possível carregar as opções de produtos.</p>
            <button type="button" onClick={() => {
              setCatalog(null)
              setCatalogAttempt((previous) => previous + 1)
            }}>Tentar carregar produtos novamente</button>
          </>
        )}
        {result === null && <p role="status">Carregando produtores…</p>}
        {result?.status === 'error' && (
          <>
            <p role="alert">Não foi possível carregar os produtores.</p>
            <button type="button" onClick={() => setProducerAttempt((previous) => previous + 1)}>
              Tentar carregar produtores novamente
            </button>
          </>
        )}
        {result?.status === 'ready' && visibleProducers.length === 0 && (
          <p role="status">
            {!result.data.baseHasProducers
              ? 'Nenhum produtor cadastrado.'
              : result.data.producers.length === 0
                ? 'Nenhum produtor fornece o produto selecionado.'
                : 'Nenhum produtor corresponde à busca.'}
          </p>
        )}
        {visibleProducers.length > 0 && (
          <ul className="producers-list">
            {visibleProducers.map(({ id, name, code, municipality, active }) => (
              <li key={id}>
                <strong>{name}</strong>
                <dl>
                  <div><dt>Código</dt><dd>{code}</dd></div>
                  <div><dt>Município</dt><dd>{municipality?.trim() || 'Não informado'}</dd></div>
                  <div><dt>Situação</dt><dd>{active ? 'Ativo' : 'Inativo'}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  )
}
