import type { Shipment } from '../api'
import { family, productName, type ProductMap } from '../products'

const MAX_PACKAGE_MASS_G = 1800 // mirrors backend/app/domain/models.py
const SHOWN = 40

type Props = { shipments: Shipment[]; products: ProductMap }

// One card per package, newest first. The bar is a scale: each segment is one
// product's grams, and the full width is the 1800 g limit.
export function ShipmentFeed({ shipments, products }: Props) {
  return (
    <section className="panel" aria-labelledby="shipments-title">
      <h2 id="shipments-title">
        Packages shipped <span className="count">{shipments.length}</span>
      </h2>
      {shipments.length === 0 ? (
        <p className="empty-state">
          Nothing has shipped yet. Place an order and restock the products it needs.
        </p>
      ) : (
        <ol className="feed">
          {shipments.slice(0, SHOWN).map((s) => (
            <li key={s.shipment_id} className="package">
              <div className="package-head">
                <span>
                  Package {s.shipment_id} for order <strong>{s.order_id}</strong>
                </span>
                <span className="muted num">
                  {s.mass_g} of {MAX_PACKAGE_MASS_G} g
                </span>
              </div>
              <div
                className="scale"
                role="img"
                aria-label={`${s.mass_g} of ${MAX_PACKAGE_MASS_G} grams`}
              >
                {s.shipped.map((line) => {
                  const product = products.get(line.product_id)
                  const grams = (product?.mass_g ?? 0) * line.quantity
                  return (
                    <span
                      key={line.product_id}
                      className={`segment ${family(product)}`}
                      style={{ width: `${(grams / MAX_PACKAGE_MASS_G) * 100}%` }}
                      title={`${line.quantity} × ${productName(products, line.product_id)}, ${grams} g`}
                    />
                  )
                })}
              </div>
              <ul className="contents">
                {s.shipped.map((line) => (
                  <li key={line.product_id}>
                    <span className={`swatch ${family(products.get(line.product_id))}`} />
                    {line.quantity} × {productName(products, line.product_id)}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {shipments.length > SHOWN && (
        <p className="muted">Showing the latest {SHOWN} packages.</p>
      )}
    </section>
  )
}
