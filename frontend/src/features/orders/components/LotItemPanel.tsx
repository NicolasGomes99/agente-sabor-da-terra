import { balanceLabel, deliveryLabel } from '../orderHelpers'
import type { LotRecord, OrderItemRecord, OrderRecord } from '../ordersApi'
import { LotTable } from './LotTable'

interface LotItemPanelProps {
  order: OrderRecord
  item: OrderItemRecord
  deletingId: string | null
  onCreate: (item: OrderItemRecord) => void
  onEdit: (item: OrderItemRecord, lot: LotRecord) => void
  onDelete: (lot: LotRecord) => void
}

export function LotItemPanel({
  order,
  item,
  deletingId,
  onCreate,
  onEdit,
  onDelete,
}: LotItemPanelProps) {
  const lots = item.lots ?? []

  return (
    <div className="lot-item">
      <header className="lot-item-header">
        <div>
          <h3>{item.product.name}</h3>
          <p className="order-muted">
            Saldo a alocar: <strong>{balanceLabel(item.balance)}</strong>
            {' '}· Prazo: {deliveryLabel(order)}
          </p>
        </div>

        {!order.cancelled && (
          <button
            className="order-button order-primary"
            type="button"
            onClick={() => onCreate(item)}
          >
            + Nova alocação
          </button>
        )}
      </header>

      {lots.length === 0 ? (
        <p className="order-muted">Nenhuma alocação registrada.</p>
      ) : (
        <LotTable
          itemName={item.product.name}
          lots={lots}
          deletingId={deletingId}
          canEdit={!order.cancelled}
          onEdit={(lot) => onEdit(item, lot)}
          onDelete={onDelete}
        />
      )}
    </div>
  )
}
