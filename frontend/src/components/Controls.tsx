import { useEffect, useRef, useState, type FormEvent } from 'react'
import sampleRestock from '../../../backend/samples/restock.json'
import { api, errorMessage, type InventoryItem, type Line, type Shipment } from '../api'

const SIMULATE_EVERY_MS = 1500

type Props = {
  inventory: InventoryItem[]
  nextOrderId: number
  onChange: () => void
}

type Feedback = { kind: 'ok' | 'error'; text: string }

function describe(shipments: Shipment[]): string {
  if (shipments.length === 0) return 'nothing shipped yet'
  const units = shipments.reduce((n, s) => n + s.shipped.reduce((m, l) => m + l.quantity, 0), 0)
  return `${units} ${units === 1 ? 'unit' : 'units'} shipped in ${shipments.length} ${
    shipments.length === 1 ? 'package' : 'packages'
  }`
}

function randomInt(min: number, max: number): number {
  return min + Math.floor(Math.random() * (max - min + 1))
}

function randomLines(inventory: InventoryItem[], count: number, maxQty: number): Line[] {
  const picked = [...inventory].sort(() => Math.random() - 0.5).slice(0, count)
  return picked.map((p) => ({ product_id: p.product_id, quantity: randomInt(1, maxQty) }))
}

export function Controls({ inventory, nextOrderId, onChange }: Props) {
  const [orderLines, setOrderLines] = useState<Line[]>([{ product_id: 0, quantity: 1 }])
  const [restockLine, setRestockLine] = useState<Line>({ product_id: 0, quantity: 5 })
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [simulating, setSimulating] = useState(false)

  async function run(action: () => Promise<string>) {
    try {
      setFeedback({ kind: 'ok', text: await action() })
    } catch (err) {
      setFeedback({ kind: 'error', text: errorMessage(err) })
    }
    onChange()
  }

  function placeOrder(e: FormEvent) {
    e.preventDefault()
    const orderId = nextOrderId
    void run(async () => {
      const result = await api.placeOrder({ order_id: orderId, requested: orderLines })
      return `Order ${orderId} placed: ${describe(result.shipments)}.`
    })
  }

  function restock(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const result = await api.restock([restockLine])
      return `Restocked. Waiting orders: ${describe(result.shipments)}.`
    })
  }

  function restockSample() {
    void run(async () => {
      const result = await api.restock(sampleRestock)
      return `Sample restock added. Waiting orders: ${describe(result.shipments)}.`
    })
  }

  // The simulator reads the latest props through a ref, so the interval isn't
  // torn down and restarted every time polling delivers new data.
  const latest = useRef({ inventory, nextOrderId, onChange })
  useEffect(() => {
    latest.current = { inventory, nextOrderId, onChange }
  })
  const simulatedId = useRef(0)

  useEffect(() => {
    if (!simulating) return
    const id = setInterval(() => {
      const { inventory, nextOrderId, onChange } = latest.current
      const tick =
        Math.random() < 0.65
          ? () => {
              // Synthetic hospital order: 1 to 3 products, a few units each.
              simulatedId.current = Math.max(simulatedId.current, nextOrderId)
              const order_id = simulatedId.current++
              return api.placeOrder({ order_id, requested: randomLines(inventory, randomInt(1, 3), 4) })
            }
          : () => api.restock(randomLines(inventory, randomInt(1, 4), 6))
      tick()
        .catch((err) => setFeedback({ kind: 'error', text: errorMessage(err) }))
        .finally(onChange)
    }, SIMULATE_EVERY_MS)
    return () => clearInterval(id)
  }, [simulating])

  const productOptions = inventory.map((p) => (
    <option key={p.product_id} value={p.product_id}>
      {p.product_name}
    </option>
  ))

  return (
    <section className="controls" aria-label="Controls">
      <form className="control" onSubmit={placeOrder}>
        <h2>New order {nextOrderId}</h2>
        {orderLines.map((line, i) => (
          <div className="line-input" key={i}>
            <select
              aria-label="Product"
              value={line.product_id}
              onChange={(e) =>
                setOrderLines(orderLines.map((l, j) => (j === i ? { ...l, product_id: Number(e.target.value) } : l)))
              }
            >
              {productOptions}
            </select>
            <input
              aria-label="Quantity"
              type="number"
              min={1}
              value={line.quantity}
              onChange={(e) =>
                setOrderLines(orderLines.map((l, j) => (j === i ? { ...l, quantity: Number(e.target.value) } : l)))
              }
            />
            {orderLines.length > 1 && (
              <button
                type="button"
                className="quiet"
                aria-label="Remove product"
                onClick={() => setOrderLines(orderLines.filter((_, j) => j !== i))}
              >
                Remove
              </button>
            )}
          </div>
        ))}
        <div className="actions">
          <button
            type="button"
            className="quiet"
            onClick={() => setOrderLines([...orderLines, { product_id: 0, quantity: 1 }])}
          >
            Add product
          </button>
          <button type="submit">Place order</button>
        </div>
      </form>

      <form className="control" onSubmit={restock}>
        <h2>Restock</h2>
        <div className="line-input">
          <select
            aria-label="Product"
            value={restockLine.product_id}
            onChange={(e) => setRestockLine({ ...restockLine, product_id: Number(e.target.value) })}
          >
            {productOptions}
          </select>
          <input
            aria-label="Quantity"
            type="number"
            min={1}
            value={restockLine.quantity}
            onChange={(e) => setRestockLine({ ...restockLine, quantity: Number(e.target.value) })}
          />
        </div>
        <div className="actions">
          <button type="button" className="quiet" onClick={restockSample}>
            Add sample restock
          </button>
          <button type="submit">Restock</button>
        </div>
      </form>

      <div className="control">
        <h2>Simulate</h2>
        <p className="muted">
          Sends a random hospital order or restock every {SIMULATE_EVERY_MS / 1000} s.
        </p>
        <div className="actions">
          <button
            type="button"
            className={simulating ? 'stop' : undefined}
            aria-pressed={simulating}
            onClick={() => setSimulating(!simulating)}
          >
            {simulating ? 'Stop simulation' : 'Start simulation'}
          </button>
        </div>
      </div>

      <p className={`feedback ${feedback?.kind ?? ''}`} role="status" aria-live="polite">
        {feedback?.text}
      </p>
    </section>
  )
}
