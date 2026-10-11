import { api } from './api'
import { usePolling } from './usePolling'

// Placeholder shell. The dashboard panels (InventoryPanel, PendingQueue,
// ShipmentFeed, Controls) are built in src/components/ once the API exists.
// See DESIGN.md, "Frontend".
export default function App() {
  const { data, error } = usePolling(api.health, 3000)

  return (
    <main>
      <header>
        <h1>Nest Fulfillment</h1>
        <p className="muted">
          Backend: {error ? 'unreachable' : data ? data.status : 'checking...'}
        </p>
      </header>
    </main>
  )
}
