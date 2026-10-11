import type { Order } from '../api'
import { family, productName, type ProductMap } from '../products'

const STATUS_LABEL = { PENDING: 'Waiting', PARTIALLY_SHIPPED: 'Partly shipped' } as const

type Props = { orders: Order[]; products: ProductMap }

// Orders that still have units to ship, oldest first: the order restocks serve them in.
export function PendingQueue({ orders, products }: Props) {
  const waiting = orders.filter((o) => o.status !== 'FULFILLED')
  const fulfilled = orders.length - waiting.length

  return (
    <section className="panel" aria-labelledby="queue-title">
      <h2 id="queue-title">
        Waiting for stock <span className="count">{waiting.length}</span>
      </h2>
      <div className="panel-body">
        {waiting.length === 0 ? (
          <p className="empty-state">No order is waiting.</p>
        ) : (
          <ol className="queue">
            {waiting.map((order) => (
              <li key={order.order_id} className="queued">
                <div className="package-head">
                  <strong>Order {order.order_id}</strong>
                  <span className={`status ${order.status.toLowerCase()}`}>
                    {STATUS_LABEL[order.status as keyof typeof STATUS_LABEL]}
                  </span>
                </div>
                <ul className="lines">
                  {order.lines.map((line) => (
                    <li key={line.product_id} className={line.remaining === 0 ? 'done' : undefined}>
                      <span className={`swatch ${family(products.get(line.product_id))}`} />
                      <span className="line-name">{productName(products, line.product_id)}</span>
                      <span className="num">
                        {line.shipped} of {line.requested}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        )}
        {fulfilled > 0 && (
          <p className="muted">
            {fulfilled} {fulfilled === 1 ? 'order' : 'orders'} fulfilled.
          </p>
        )}
      </div>
    </section>
  )
}
