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

// Form fields hold the raw text the user typed. Binding a number straight to
// <input type="number"> leaves stray leading zeros ("04") on screen.
type DraftLine = { product_id: number; quantity: string }

function toLines(drafts: DraftLine[]): Line[] {
  return drafts.map((d) => ({ product_id: d.product_id, quantity: Number(d.quantity) }))
}

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

// The nest operator doesn't create orders or stock: hospitals and suppliers do,
// by calling the API. This column stands in for those outside systems.
export function OutsideInputs({ inventory, nextOrderId, onChange }: Props) {
  const [orderId, setOrderId] = useState('') // empty means "use nextOrderId"
  const [orderLines, setOrderLines] = useState<DraftLine[]>([{ product_id: 0, quantity: '1' }])
  const [restockLine, setRestockLine] = useState<DraftLine>({ product_id: 0, quantity: '5' })
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

  function sendOrder(e: FormEvent) {
    e.preventDefault()
    const id = orderId === '' ? nextOrderId : Number(orderId)
    void run(async () => {
      const result = await api.placeOrder({ order_id: id, requested: toLines(orderLines) })
      setOrderId('')
      return `Order ${id} received: ${describe(result.shipments)}.`
    })
  }

  function deliverRestock(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const result = await api.restock(toLines([restockLine]))
      return `Restock delivered. Waiting orders: ${describe(result.shipments)}.`
    })
  }

  function deliverSampleRestock() {
    void run(async () => {
      const result = await api.restock(sampleRestock)
      return `Sample restock delivered. Waiting orders: ${describe(result.shipments)}.`
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

  function updateOrderLine(i: number, change: Partial<DraftLine>) {
    setOrderLines(orderLines.map((l, j) => (j === i ? { ...l, ...change } : l)))
  }

  return (
    <aside className="outside" aria-labelledby="outside-title">
      <h2 id="outside-title">Outside the nest</h2>
      <p className="muted">
        Stand-ins for the hospital and supplier systems that call this nest's API.
      </p>

      <p className={`feedback ${feedback?.kind ?? ''}`} role="status" aria-live="polite">
        {feedback?.text}
      </p>

      <form className="actor" onSubmit={sendOrder}>
        <h3>Hospital</h3>
        <label className="field">
          <span>Order id</span>
          <input
            type="number"
            min={0}
            placeholder={String(nextOrderId)}
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
        </label>
        {orderLines.map((line, i) => (
          <div className="line-input" key={i}>
            <select
              aria-label="Product"
              value={line.product_id}
              onChange={(e) => updateOrderLine(i, { product_id: Number(e.target.value) })}
            >
              {productOptions}
            </select>
            <input
              aria-label="Quantity"
              type="number"
              min={1}
              value={line.quantity}
              onChange={(e) => updateOrderLine(i, { quantity: e.target.value })}
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
            onClick={() => setOrderLines([...orderLines, { product_id: 0, quantity: '1' }])}
          >
            Add product
          </button>
          <button type="submit">Send order</button>
        </div>
      </form>

      <form className="actor" onSubmit={deliverRestock}>
        <h3>Supplier</h3>
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
            onChange={(e) => setRestockLine({ ...restockLine, quantity: e.target.value })}
          />
        </div>
        <div className="actions">
          <button type="button" className="quiet" onClick={deliverSampleRestock}>
            Deliver sample restock
          </button>
          <button type="submit">Deliver restock</button>
        </div>
      </form>

      <div className="actor">
        <h3>Demo</h3>
        <p className="muted">
          Plays both roles: a random hospital order or supplier restock every{' '}
          {SIMULATE_EVERY_MS / 1000} s.
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
    </aside>
  )
}
