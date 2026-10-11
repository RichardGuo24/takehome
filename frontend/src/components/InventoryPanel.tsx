import type { InventoryItem, Order } from '../api'
import { family } from '../products'

type Props = { inventory: InventoryItem[]; orders: Order[] }

// Stock per product next to what waiting orders still need. The two columns make
// invariant I4 visible: a product is never both in stock and waited for.
export function InventoryPanel({ inventory, orders }: Props) {
  const waitingFor = new Map<number, number>()
  for (const order of orders) {
    for (const line of order.lines) {
      waitingFor.set(line.product_id, (waitingFor.get(line.product_id) ?? 0) + line.remaining)
    }
  }

  return (
    <section className="panel" aria-labelledby="inventory-title">
      <h2 id="inventory-title">Inventory</h2>
      <table className="inventory">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col" className="num">
              Mass
            </th>
            <th scope="col" className="num">
              In stock
            </th>
            <th scope="col" className="num">
              Waiting
            </th>
          </tr>
        </thead>
        <tbody>
          {inventory.map((item) => {
            const waiting = waitingFor.get(item.product_id) ?? 0
            return (
              <tr key={item.product_id} className={item.quantity === 0 ? 'empty' : undefined}>
                <td>
                  <span className={`swatch ${family(item)}`} aria-hidden="true" />
                  {item.product_name}
                </td>
                <td className="num muted">{item.mass_g} g</td>
                <td className="num stock">{item.quantity}</td>
                <td className={waiting > 0 ? 'num short' : 'num muted'}>{waiting || ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
