import type { InventoryItem, Order, Shipment } from '../api'
import { MAX_PACKAGE_MASS_G } from '../products'

type Props = { inventory: InventoryItem[]; orders: Order[]; shipments: Shipment[] }

// Four headline numbers for the operator. All derived from the same poll as the panels.
export function StatTiles({ inventory, orders, shipments }: Props) {
  const unitsInStock = inventory.reduce((n, p) => n + p.quantity, 0)
  const waiting = orders.filter((o) => o.status !== 'FULFILLED')
  const unitsWaiting = waiting.reduce(
    (n, o) => n + o.lines.reduce((m, l) => m + l.remaining, 0),
    0,
  )
  const fulfilled = orders.length - waiting.length
  const avgFill =
    shipments.length === 0
      ? null
      : shipments.reduce((n, s) => n + s.mass_g, 0) / shipments.length / MAX_PACKAGE_MASS_G

  return (
    <dl className="stats">
      <div className="stat">
        <dt>Units in stock</dt>
        <dd>{unitsInStock}</dd>
        <p>across {inventory.filter((p) => p.quantity > 0).length} of {inventory.length} products</p>
      </div>
      <div className="stat">
        <dt>Orders waiting</dt>
        <dd>{waiting.length}</dd>
        <p>{unitsWaiting} units short</p>
      </div>
      <div className="stat">
        <dt>Packages shipped</dt>
        <dd>{shipments.length}</dd>
        <p>
          {fulfilled} {fulfilled === 1 ? 'order' : 'orders'} fulfilled
        </p>
      </div>
      <div className="stat">
        <dt>Average package fill</dt>
        <dd>{avgFill === null ? 'None yet' : `${Math.round(avgFill * 100)}%`}</dd>
        <p>of the {MAX_PACKAGE_MASS_G} g limit</p>
      </div>
    </dl>
  )
}
