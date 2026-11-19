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
  createOrder,
  getOrder,
  listOrders,
  updateOrder,
  type OrderRecord,
} from '../../src/features/orders/ordersApi'
import { listProducts } from '../../src/features/registry/registryApi'
import { ApiError } from '../../src/lib/api-client'
import { setAccessToken } from '../../src/lib/auth-storage'

vi.mock('../../src/features/orders/ordersApi', () => ({
  listOrders: vi.fn(),
  getOrder: vi.fn(),
  createOrder: vi.fn(),
  updateOrder: vi.fn(),
  cancelOrder: vi.fn(),
}))

vi.mock('../../src/features/registry/registryApi', () => ({
  listProducts: vi.fn(),
}))

const tomato = { id: 'tomato-id', name: 'Tomate' }
const lettuce = { id: 'lettuce-id', name: 'Alface' }

const item = {
  id: 'item-id',
  product_id: tomato.id,
  product: tomato,
  quantity: '10.000',
  unit: 'kg',
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

const catalog = vi.mocked(listProducts)
const list = vi.mocked(listOrders)
const get = vi.mocked(getOrder)
const create = vi.mocked(createOrder)
const update = vi.mocked(updateOrder)
const cancel = vi.mocked(cancelOrder)

function openPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

async function fillCreate() {
  await screen.findByRole('option', { name: 'Tomate' })

  fireEvent.change(screen.getByLabelText(/Comprador/), {
    target: { value: 'Mercado de teste' },
  })

  fireEvent.change(screen.getByLabelText('Produto 1 *'), {
    target: { value: tomato.id },
  })

  fireEvent.change(screen.getByLabelText('Quantidade 1 *'), {
    target: { value: '10,125' },
  })

  fireEvent.change(screen.getByLabelText('Unidade 1 *'), {
    target: { value: 'kg' },
  })

  fireEvent.change(screen.getByLabelText(/Data de entrega/), {
    target: { value: '2026-12-05' },
  })
}

describe('Telas de pedidos', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    setAccessToken('test-token')

    catalog.mockResolvedValue([tomato, lettuce])
    list.mockResolvedValue([order])
    get.mockResolvedValue(order)
    create.mockResolvedValue(order)
    update.mockResolvedValue(order)
    cancel.mockResolvedValue({
      ...order,
      cancelled: true,
    })

    // O ambiente de testes não implementa os métodos do dialog.
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute('open', '')
    }

    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute('open')
    }
  })

  it('exige login para acessar Pedidos', () => {
    localStorage.clear()

    openPage('/orders')

    expect(
      screen.getByRole('heading', {
        name: 'Acesso à cooperativa',
      }),
    ).toBeTruthy()

    expect(list).not.toHaveBeenCalled()
  })

  it('lista pedidos e permite buscar pelo produto', async () => {
    openPage('/orders')

    await screen.findByText('Mercado de teste')

    fireEvent.change(screen.getByLabelText('Buscar pedido'), {
      target: { value: 'tomate' },
    })

    expect(screen.getByText('Mercado de teste')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Buscar pedido'), {
      target: { value: 'produto inexistente' },
    })

    expect(
      screen.getByText(/Nenhum pedido encontrado/),
    ).toBeTruthy()
  })

  it('cadastra dois produtos com quantidades decimais', async () => {
    const secondItem = {
      id: 'second-item-id',
      product_id: lettuce.id,
      product: lettuce,
      quantity: '5',
      unit: 'un',
    }

    const saved: OrderRecord = {
      ...order,
      items: [
        { ...item, quantity: '10.125' },
        secondItem,
      ],
    }

    create.mockResolvedValue(saved)
    get.mockResolvedValue(saved)

    openPage('/orders/new')
    await fillCreate()

    fireEvent.click(
      screen.getByRole('button', {
        name: '+ Adicionar item',
      }),
    )

    fireEvent.change(screen.getByLabelText('Produto 2 *'), {
      target: { value: lettuce.id },
    })

    fireEvent.change(screen.getByLabelText('Quantidade 2 *'), {
      target: { value: '5' },
    })

    fireEvent.change(screen.getByLabelText('Unidade 2 *'), {
      target: { value: 'un' },
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Cadastrar pedido',
      }),
    )

    await waitFor(() => {
      expect(create).toHaveBeenCalledExactlyOnceWith({
        buyer: 'Mercado de teste',
        conditions: '',
        delivery_start_date: '2026-12-05',
        delivery_end_date: null,
        items: [
          {
            product_id: tomato.id,
            quantity: '10.125',
            unit: 'kg',
          },
          {
            product_id: lettuce.id,
            quantity: '5',
            unit: 'un',
          },
        ],
      })
    })

    const table = await screen.findByRole('table', {
      name: 'Itens do pedido',
    })

    expect(within(table).getByText('Tomate')).toBeTruthy()
    expect(within(table).getByText('Alface')).toBeTruthy()
  })

  it('mantém o ID ao editar quantidade e unidade', async () => {
    openPage('/orders/order-id/edit')

    await screen.findByRole('option', { name: 'Tomate' })

    fireEvent.change(screen.getByLabelText('Quantidade 1 *'), {
      target: { value: '12,500' },
    })

    fireEvent.change(screen.getByLabelText('Unidade 1 *'), {
      target: { value: 'caixa' },
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Salvar alterações',
      }),
    )

    await waitFor(() => {
      expect(update).toHaveBeenCalledExactlyOnceWith(
        order.id,
        expect.objectContaining({
          version: order.version,
          items: [
            {
              id: item.id,
              product_id: tomato.id,
              quantity: '12.500',
              unit: 'caixa',
            },
          ],
        }),
      )
    })
  })

  it('preserva os campos quando a API rejeita uma edição', async () => {
    update.mockRejectedValue(
      new ApiError(422, { detail: 'Dados inválidos' }),
    )

    openPage('/orders/order-id/edit')

    await screen.findByRole('option', { name: 'Tomate' })

    const buyer = screen.getByLabelText(/Comprador/)

    fireEvent.change(buyer, {
      target: { value: 'Comprador atualizado' },
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Salvar alterações',
      }),
    )

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect((buyer as HTMLInputElement).value).toBe(
      'Comprador atualizado',
    )
  })

  it.each(['0', '-1', 'NaN', '1.2345'])(
    'rejeita a quantidade inválida %s antes de enviar',
    async (quantity) => {
      openPage('/orders/new')
      await fillCreate()

      fireEvent.change(screen.getByLabelText('Quantidade 1 *'), {
        target: { value: quantity },
      })

      const button = screen.getByRole('button', {
        name: 'Cadastrar pedido',
      })

      fireEvent.submit(button.closest('form')!)

      expect(screen.getByRole('alert').textContent).toContain(
        'quantidade positiva',
      )
      expect(create).not.toHaveBeenCalled()
    },
  )

  it('rejeita unidade composta apenas por espaços', async () => {
    openPage('/orders/new')
    await fillCreate()

    fireEvent.change(screen.getByLabelText('Unidade 1 *'), {
      target: { value: '   ' },
    })

    const button = screen.getByRole('button', {
      name: 'Cadastrar pedido',
    })

    fireEvent.submit(button.closest('form')!)

    expect(screen.getByRole('alert')).toBeTruthy()
    expect(create).not.toHaveBeenCalled()
  })

  it('rejeita um intervalo de datas invertido', async () => {
    openPage('/orders/new')
    await fillCreate()

    fireEvent.click(
      screen.getByLabelText('Entrega em um intervalo de datas'),
    )

    fireEvent.change(screen.getByLabelText(/Data final/), {
      target: { value: '2026-12-04' },
    })

    const button = screen.getByRole('button', {
      name: 'Cadastrar pedido',
    })

    fireEvent.submit(button.closest('form')!)

    expect(screen.getByRole('alert').textContent).toContain(
      'A data final deve ser igual ou posterior',
    )
    expect(create).not.toHaveBeenCalled()
  })

  it('estrutura um pedido antigo sem reenviar sua descrição', async () => {
    const legacy: OrderRecord = {
      ...order,
      products: '  Tomate: 10 kg\nAlface: 5 unidades  ',
      items: [],
      needs_item_structuring: true,
    }

    get.mockResolvedValue(legacy)

    openPage('/orders/order-id/edit')
    await fillCreate()

    expect(
      screen.getByText(/Tomate: 10 kg/).textContent,
    ).toBe(legacy.products)

    expect(
      screen.getByText(/Este pedido ainda não tem itens estruturados/),
    ).toBeTruthy()

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Salvar alterações',
      }),
    )

    await waitFor(() => {
      expect(update).toHaveBeenCalledOnce()
    })

    const payload = update.mock.calls[0][1]

    expect(payload).not.toHaveProperty('products')
    expect(payload.items).toEqual([
      {
        product_id: tomato.id,
        quantity: '10.125',
        unit: 'kg',
      },
    ])
  })

  it('exige confirmação e mantém os itens após cancelar', async () => {
    openPage('/orders/order-id')

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Cancelar pedido',
      }),
    )

    expect(cancel).not.toHaveBeenCalled()

    const dialog = screen.getByRole('dialog')

    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'Confirmar cancelamento',
      }),
    )

    expect(await screen.findByText('Cancelado')).toBeTruthy()
    expect(cancel).toHaveBeenCalledExactlyOnceWith(order.id)

    const table = screen.getByRole('table', {
      name: 'Itens do pedido',
    })

    expect(within(table).getByText('Tomate')).toBeTruthy()

    expect(
      screen.queryByRole('link', { name: 'Editar pedido' }),
    ).toBeNull()
  })

  it('bloqueia a edição direta de um pedido cancelado', async () => {
    get.mockResolvedValue({
      ...order,
      cancelled: true,
    })

    openPage('/orders/order-id/edit')

    expect((await screen.findByRole('alert')).textContent).toContain(
      'não pode ser editado',
    )

    expect(
      screen.queryByRole('button', {
        name: 'Salvar alterações',
      }),
    ).toBeNull()

    expect(update).not.toHaveBeenCalled()
  })

  it('bloqueia o cadastro quando o catálogo está vazio', async () => {
    catalog.mockResolvedValue([])

    openPage('/orders/new')

    expect(
      await screen.findByText(/Nenhum produto cadastrado/),
    ).toBeTruthy()

    const button = screen.getByRole('button', {
      name: 'Cadastrar pedido',
    })

    expect(button.hasAttribute('disabled')).toBe(true)
    expect(create).not.toHaveBeenCalled()
  })
  it('preserva o formulário em conflito e só usa a nova versão após recarregar', async () => {
    update.mockRejectedValueOnce(new ApiError(409, {
      detail: { code: 'order_version_conflict', message: 'Pedido alterado.' },
    }))
    openPage('/orders/order-id/edit')
    await screen.findByRole('option', { name: 'Tomate' })
    const buyer = screen.getByLabelText(/Comprador/)
    fireEvent.change(buyer, { target: { value: 'Minha edição' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))
    expect((await screen.findByRole('alert')).textContent).toContain('alterado por outra operação')
    expect((buyer as HTMLInputElement).value).toBe('Minha edição')
    expect(screen.getByRole('button', { name: 'Salvar alterações' }).hasAttribute('disabled')).toBe(true)
    expect(update.mock.calls[0][1].version).toBe(1)

    const current: OrderRecord = {
      ...order, version: 2, buyer: 'Outra pessoa salvou',
      items: [...order.items, {
        id: 'new-item-id', product_id: lettuce.id, product: lettuce, quantity: '5', unit: 'un',
      }],
    }
    get.mockResolvedValue(current)
    update.mockResolvedValue({ ...current, version: 3 })
    fireEvent.click(screen.getByRole('button', { name: 'Recarregar pedido' }))
    await screen.findAllByRole('option', { name: 'Tomate' })
    expect((screen.getByLabelText(/Comprador/) as HTMLInputElement).value).toBe(current.buyer)
    expect(screen.getByLabelText('Produto 2 *')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Unidade 1 *'), { target: { value: 'caixa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2))
    expect(update.mock.calls[1][1].version).toBe(2)
    expect(update.mock.calls[1][1].items.map((entry) => entry.id)).toEqual([item.id, 'new-item-id'])
  })

})