import { useState } from 'react'
import sampleCatalog from '../../backend/samples/catalog.json'
import { api, errorMessage } from './api'
import { InventoryPanel } from './components/InventoryPanel'
import { OutsideInputs } from './components/OutsideInputs'
import { PendingQueue } from './components/PendingQueue'
import { ShipmentFeed } from './components/ShipmentFeed'
import { StatTiles } from './components/StatTiles'
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

  const ready = data !== null && data.inventory.length > 0

  return (
    <div className="app">
      {/* The sidebar is outside the nest: stand-ins for the systems that call the API. */}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <h1>Nest fulfillment</h1>
        </div>
        {ready ? (
          <OutsideInputs inventory={data.inventory} nextOrderId={nextOrderId} onChange={refresh} />
        ) : (
          <p className="hint">Hospital, supplier, and demo controls appear once the catalog is loaded.</p>
        )}
      </aside>

      {/* The main area is the operator's view. Read only: nothing here changes state. */}
      <main className="main">
        <header className="main-head">
          <h2>Operator view</h2>
          <p className={error ? 'connection down' : 'connection'}>
            {error ? errorMessage(error) : data ? 'Live, updates every 1.5 s' : 'Connecting...'}
          </p>
        </header>

        {data && !ready && (
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

        {ready && (
          <>
            <StatTiles inventory={data.inventory} orders={data.orders} shipments={data.shipments} />
            <div className="board">
              <InventoryPanel inventory={data.inventory} orders={data.orders} />
              <ShipmentFeed shipments={data.shipments} products={products} />
              <PendingQueue orders={data.orders} products={products} />
            </div>
          </>
        )}
      </main>
    </div>
  )
}
