import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../../src/app/routes'
import { AuthProvider } from '../../src/features/auth/AuthContext'
import {
  cancelOrder,
  createLot,
  deleteLot,
  getOrder,
  listOrders,
  updateLot,
  type LotRecord,
  type OrderRecord,
} from '../../src/features/orders/ordersApi'
import { listProducers } from '../../src/features/registry/registryApi'
import { ApiError } from '../../src/lib/api-client'
import { setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/orders/ordersApi', () => ({
  listOrders: vi.fn(),
  getOrder: vi.fn(),
  createOrder: vi.fn(),
  updateOrder: vi.fn(),
  cancelOrder: vi.fn(),
  createLot: vi.fn(),
  updateLot: vi.fn(),
  deleteLot: vi.fn(),
}))

vi.mock('../../src/features/registry/registryApi', () => ({
  listProducts: vi.fn(),
  listProducers: vi.fn(),
}))

const tomato = { id: 'tomato-id', name: 'Tomate' }

const producerAna = {
  id: 'ana-id',
  code: 'P001',
  name: 'Ana Silva',
  cpf: '01234567890',
  active: true,
  phone: null,
  email: null,
  address: null,
  municipality: null,
  products: [tomato],
}

const item = {
  id: 'item-id',
  product_id: tomato.id,
  product: tomato,
  quantity: '100.000',
  unit: 'kg',
  lots: [] as LotRecord[],
  balance: '100.000',
}

const order: OrderRecord = {
  id: 'order-id',
  buyer: 'Mercado de teste',
  conditions: '',
  delivery_start_date: '2026-12-05',
  delivery_end_date: null,
  session_id: null,
  version: 1,
  cancelled: false,
  products: '',
  needs_item_structuring: false,
  items: [item],
}

const lot = {
  id: 'lot-id',
  item_id: item.id,
  producer: { id: producerAna.id, name: producerAna.name },
  quantity: '40.000',
  unit: 'kg',
  delivery_date: '2026-12-05',
  availability_confirmed: true,
}

const get = vi.mocked(getOrder)
const list = vi.mocked(listOrders)
const cancel = vi.mocked(cancelOrder)
const create = vi.mocked(createLot)
const update = vi.mocked(updateLot)
const remove = vi.mocked(deleteLot)
const producers = vi.mocked(listProducers)

function openPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Alocações por item', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    setAccessToken('test-token')

    list.mockResolvedValue([order])
    get.mockResolvedValue(order)
    cancel.mockResolvedValue({ ...order, cancelled: true })
    producers.mockResolvedValue([producerAna])
    create.mockResolvedValue(lot)
    update.mockResolvedValue(lot)
    remove.mockResolvedValue(undefined)

    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute('open', '')
    }
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute('open')
    }
  })

  it('mostra o prazo aceito e o saldo a alocar por item', async () => {
    openPage('/orders/order-id')

    expect(
      await screen.findByRole('heading', { name: 'Alocações por item' }),
    ).toBeTruthy()

    expect(screen.getByText(/Saldo a alocar:/).textContent).toContain(
      '100.000',
    )
    expect(screen.getByText(/Prazo:/).textContent).toContain('05/12/2026')
    expect(screen.getByText('Nenhuma alocação registrada.')).toBeTruthy()
  })

  it('lista as alocações existentes com produtor e data', async () => {
    get.mockResolvedValue({
      ...order,
      items: [
        {
          ...item,
          lots: [lot],
          balance: '60.000',
        },
      ],
    })

    openPage('/orders/order-id')

    expect(await screen.findByText('Ana Silva')).toBeTruthy()

    const table = screen.getByRole('table', {
      name: 'Alocações de Tomate',
    })
    expect(within(table).getByText('40.000')).toBeTruthy()
    expect(within(table).getByText('05/12/2026')).toBeTruthy()
    expect(within(table).getByText('Confirmada')).toBeTruthy()
    expect(screen.getByText(/Saldo a alocar:/).textContent).toContain('60.000')
  })

  it('cadastra uma alocação com confirmação de disponibilidade', async () => {
    openPage('/orders/order-id')

    fireEvent.click(
      await screen.findByRole('button', { name: '+ Nova alocação' }),
    )

    const dialog = await screen.findByRole('dialog')
    expect(producers).toHaveBeenCalledWith(
      item.product_id,
      expect.any(AbortSignal),
    )

    fireEvent.change(within(dialog).getByLabelText(/Produtor/), {
      target: { value: producerAna.id },
    })
    fireEvent.change(within(dialog).getByLabelText(/Quantidade/), {
      target: { value: '40' },
    })
    fireEvent.change(within(dialog).getByLabelText(/Unidade/), {
      target: { value: 'kg' },
    })
    fireEvent.click(within(dialog).getByLabelText(/Confirmo a disponibilidade/))

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Adicionar alocação' }),
    )

    await waitFor(() => {
      expect(create).toHaveBeenCalledExactlyOnceWith(
        order.id,
        item.id,
        {
          producer_id: producerAna.id,
          quantity: '40',
          unit: 'kg',
          delivery_date: '2026-12-05',
          availability_confirmed: true,
        },
      )
    })
  })

  it('mostra o motivo retornado pelo backend ao rejeitar uma alocação', async () => {
    create.mockRejectedValue(
      new ApiError(422, {
        detail: 'O produtor João Silva está inativo e não pode atender a este item.',
      }),
    )

    openPage('/orders/order-id')

    fireEvent.click(
      await screen.findByRole('button', { name: '+ Nova alocação' }),
    )

    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText(/Produtor/), {
      target: { value: producerAna.id },
    })
    fireEvent.change(within(dialog).getByLabelText(/Quantidade/), {
      target: { value: '40' },
    })
    fireEvent.click(within(dialog).getByLabelText(/Confirmo a disponibilidade/))

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Adicionar alocação' }),
    )

    expect(
      await within(dialog).findByText(/inativo e não pode atender/),
    ).toBeTruthy()
  })

  it('exige confirmação antes de cadastrar', async () => {
    openPage('/orders/order-id')

    fireEvent.click(
      await screen.findByRole('button', { name: '+ Nova alocação' }),
    )

    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText(/Produtor/), {
      target: { value: producerAna.id },
    })
    fireEvent.change(within(dialog).getByLabelText(/Quantidade/), {
      target: { value: '40' },
    })

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Adicionar alocação' }),
    )

    expect(await within(dialog).findByRole('alert')).toBeTruthy()
    expect(create).not.toHaveBeenCalled()
  })

  it('edita uma alocação reenviando os dados com nova confirmação', async () => {
    get.mockResolvedValue({
      ...order,
      items: [{ ...item, lots: [lot], balance: '60.000' }],
    })

    openPage('/orders/order-id')

    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))

    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText(/Quantidade/), {
      target: { value: '50' },
    })
    fireEvent.click(within(dialog).getByLabelText(/Confirmo a disponibilidade/))

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Salvar alocação' }),
    )

    await waitFor(() => {
      expect(update).toHaveBeenCalledExactlyOnceWith(lot.id, {
        producer_id: producerAna.id,
        quantity: '50',
        unit: 'kg',
        delivery_date: '2026-12-05',
        availability_confirmed: true,
      })
    })
  })

  it('exclui uma alocação e recarrega o pedido', async () => {
    get.mockResolvedValueOnce({
      ...order,
      items: [{ ...item, lots: [lot], balance: '60.000' }],
    })
    get.mockResolvedValueOnce({
      ...order,
      items: [{ ...item, lots: [], balance: '100.000' }],
    })

    openPage('/orders/order-id')

    fireEvent.click(await screen.findByRole('button', { name: 'Excluir' }))

    await waitFor(() => {
      expect(remove).toHaveBeenCalledExactlyOnceWith(lot.id)
    })
  })

  it('oculta as ações de alocação em um pedido cancelado', async () => {
    get.mockResolvedValue({ ...order, cancelled: true })

    openPage('/orders/order-id')

    await screen.findByRole('heading', { name: 'Alocações por item' })

    expect(
      screen.queryByRole('button', { name: '+ Nova alocação' }),
    ).toBeNull()
  })
})
