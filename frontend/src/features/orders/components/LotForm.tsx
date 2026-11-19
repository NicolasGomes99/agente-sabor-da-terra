import { useState, type FormEvent } from "react";

import type { Producer } from "../../registry/types";
import type {
  LotInput,
  LotRecord,
  OrderItemRecord,
  OrderRecord,
} from "../ordersApi";
import { buildUnitOptions, validateLotForm } from "../utils/lotForm";

interface LotFormProps {
  order: OrderRecord;
  item: OrderItemRecord;
  initial?: LotRecord;
  producers: Producer[];
  pending: boolean;
  error: string | null;
  onSubmit: (data: LotInput) => Promise<void>;
  onCancel: () => void;
}

export function LotForm({
  order,
  item,
  initial,
  producers,
  pending,
  error,
  onSubmit,
  onCancel,
}: LotFormProps) {
  const [producerId, setProducerId] = useState(initial?.producer.id ?? "");
  const [quantity, setQuantity] = useState(initial?.quantity ?? "");
  const [unit, setUnit] = useState(initial?.unit ?? item.unit);
  const [deliveryDate, setDeliveryDate] = useState(
    initial?.delivery_date ?? order.delivery_start_date,
  );
  const [confirmed, setConfirmed] = useState(
    initial?.availability_confirmed === true,
  );
  const [validation, setValidation] = useState<string | null>(null);

  const minDate = order.delivery_start_date;
  const maxDate = order.delivery_end_date ?? order.delivery_start_date;
  const unitOptions = buildUnitOptions(item.unit, initial?.unit);

  const hasChanges =
    !initial ||
    initial.producer.id !== producerId ||
    initial.quantity !== quantity ||
    initial.unit !== unit ||
    initial.delivery_date !== deliveryDate;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (pending) return;

    const result = validateLotForm({
      producerId,
      quantity,
      unit,
      deliveryDate,
      confirmed,
    });

    if (result.error || !result.input) {
      setValidation(result.error ?? "Confira os dados antes de salvar.");
      return;
    }

    setValidation(null);
    await onSubmit(result.input);
  }

  function touch<T>(apply: (value: T) => void, value: T) {
    apply(value);
    if (initial && !confirmed) return;
    setConfirmed(false);
  }

  return (
    <form className="order-form lot-form" onSubmit={submit} aria-busy={pending}>
      <p className="order-muted">
        Item: <strong>{item.product.name}</strong> — {item.quantity} {item.unit}
      </p>

      <label htmlFor="lot-producer">
        Produtor <span aria-hidden="true">*</span>
      </label>
      <select
        id="lot-producer"
        required
        disabled={pending}
        value={producerId}
        onChange={(event) => touch(setProducerId, event.target.value)}
      >
        <option value="">Selecione um produtor</option>
        {producers.map((producer) => (
          <option key={producer.id} value={producer.id}>
            {producer.name}
          </option>
        ))}
      </select>

      <label htmlFor="lot-quantity">
        Quantidade <span aria-hidden="true">*</span>
      </label>
      <input
        id="lot-quantity"
        required
        inputMode="decimal"
        disabled={pending}
        placeholder="Ex.: 10,500"
        value={quantity}
        onChange={(event) => touch(setQuantity, event.target.value)}
      />

      <label htmlFor="lot-unit">
        Unidade <span aria-hidden="true">*</span>
      </label>
      <select
        id="lot-unit"
        required
        disabled={pending}
        value={unit}
        onChange={(event) => touch(setUnit, event.target.value)}
      >
        {unitOptions.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>

      <label htmlFor="lot-delivery-date">
        Data prevista de entrega <span aria-hidden="true">*</span>
      </label>
      <input
        id="lot-delivery-date"
        type="date"
        required
        disabled={pending}
        min={minDate}
        max={maxDate}
        value={deliveryDate}
        onChange={(event) => touch(setDeliveryDate, event.target.value)}
      />

      <label className="order-checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={pending}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmo a disponibilidade do produtor para esta quantidade, unidade e
        data.
      </label>

      {(validation || error) && (
        <p className="order-error" role="alert">
          {validation || error}
        </p>
      )}

      <div className="order-form-footer">
        <span className="order-muted">
          {hasChanges && initial
            ? "Os dados mudaram: confirme a disponibilidade novamente."
            : "* Campos obrigatórios"}
        </span>

        <div className="order-actions">
          <button
            className="order-button"
            type="button"
            disabled={pending}
            onClick={onCancel}
          >
            Cancelar
          </button>

          <button
            className="order-button order-primary"
            type="submit"
            disabled={pending}
          >
            {pending
              ? "Salvando…"
              : initial
                ? "Salvar alocação"
                : "Adicionar alocação"}
          </button>
        </div>
      </div>
    </form>
  );
}
