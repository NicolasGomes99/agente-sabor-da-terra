import { availabilityLabel, formatDate } from '../orderHelpers'
import type { LotRecord } from '../ordersApi'

interface LotTableProps {
  itemName: string
  lots: LotRecord[]
  deletingId: string | null
  canEdit: boolean
  onEdit: (lot: LotRecord) => void
  onDelete: (lot: LotRecord) => void
}

export function LotTable({
  itemName,
  lots,
  deletingId,
  canEdit,
  onEdit,
  onDelete,
}: LotTableProps) {
  return (
    <div className="order-table-scroll">
      <table className="order-table">
        <caption className="sr-only">Alocações de {itemName}</caption>
        <thead>
          <tr>
            <th scope="col">Produtor</th>
            <th scope="col">Quantidade</th>
            <th scope="col">Unidade</th>
            <th scope="col">Entrega</th>
            <th scope="col">Disponibilidade</th>
            <th scope="col">Ações</th>
          </tr>
        </thead>
        <tbody>
          {lots.map((lot) => (
            <tr key={lot.id}>
              <td>{lot.producer.name}</td>
              <td>{lot.quantity}</td>
              <td>{lot.unit ?? '—'}</td>
              <td>{formatDate(lot.delivery_date)}</td>
              <td>{availabilityLabel(lot.availability_confirmed)}</td>
              <td>
                {canEdit && (
                  <div className="order-actions">
                    <button
                      className="order-text-link"
                      type="button"
                      onClick={() => onEdit(lot)}
                    >
                      Editar
                    </button>
                    <button
                      className="order-text-link"
                      type="button"
                      disabled={deletingId === lot.id}
                      onClick={() => onDelete(lot)}
                    >
                      Excluir
                    </button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
