import { useState } from 'react'
import sampleCatalog from '../../backend/samples/catalog.json'
import { api, errorMessage } from './api'
import { Controls } from './components/Controls'
import { InventoryPanel } from './components/InventoryPanel'
import { PendingQueue } from './components/PendingQueue'
import { ShipmentFeed } from './components/ShipmentFeed'
import type { ProductMap } from './products'
import { usePolling } from './usePolling'

// One poll fetches everything the panels show, so they always agree with each other.
// Defined at module level so usePolling gets a stable function.
async function loadSnapshot() {
  const [inventory, orders, shipments] = await Promise.all([
    api.inventory(),
    api.orders(),
    api.shipments(),
  ])
  return { inventory, orders, shipments }
}

export default function App() {
  const { data, error, refresh } = usePolling(loadSnapshot, 1500)
  const [setupError, setSetupError] = useState<string | null>(null)

  async function loadCatalog() {
    try {
      await api.initCatalog(sampleCatalog)
      setSetupError(null)
    } catch (err) {
      setSetupError(errorMessage(err))
    }
    void refresh()
  }

  const products: ProductMap = new Map(data?.inventory.map((p) => [p.product_id, p]))
  // Suggest ids from 1 up. Hospitals may send any id; this only fills the form.
  const nextOrderId = Math.max(1, ...(data?.orders.map((o) => o.order_id + 1) ?? []))

  return (
    <main>
      <header className="masthead">
        <h1>Nest fulfillment</h1>
        <p className={error ? 'connection down' : 'connection'}>
          {error ? errorMessage(error) : data ? 'Live, updates every 1.5 s' : 'Connecting...'}
        </p>
      </header>

      {data && data.inventory.length === 0 && (
        <section className="setup">
          <h2>No catalog yet</h2>
          <p>
            The nest needs to know which products it stocks before it can take orders. Load the
            13 blood products from the assignment to start with zero of each.
          </p>
          <button type="button" onClick={loadCatalog}>
            Load sample catalog
          </button>
          {setupError && <p className="feedback error">{setupError}</p>}
        </section>
      )}

      {data && data.inventory.length > 0 && (
        <>
          <Controls inventory={data.inventory} nextOrderId={nextOrderId} onChange={refresh} />
          <div className="board">
            <InventoryPanel inventory={data.inventory} orders={data.orders} />
            <ShipmentFeed shipments={data.shipments} products={products} />
            <PendingQueue orders={data.orders} products={products} />
          </div>
        </>
      )}
    </main>
  )
}
