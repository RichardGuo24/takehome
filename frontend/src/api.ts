// Hand-written types mirroring the backend's Pydantic schemas (backend/app/api/schemas.py).
// There are only a handful, so codegen isn't worth the setup. Keep the two in sync.

export type ProductIn = { product_id: number; product_name: string; mass_g: number }
export type Line = { product_id: number; quantity: number }
export type OrderIn = { order_id: number; requested: Line[] }

export type Product = ProductIn
export type InventoryItem = Product & { quantity: number }
export type OrderStatus = 'PENDING' | 'PARTIALLY_SHIPPED' | 'FULFILLED'
export type OrderLineStatus = {
  product_id: number
  requested: number
  shipped: number
  remaining: number
}
export type Order = { order_id: number; seq: number; status: OrderStatus; lines: OrderLineStatus[] }
export type Shipment = { shipment_id: number; order_id: number; shipped: Line[]; mass_g: number }
export type OrderResult = { order: Order; shipments: Shipment[] }
export type RestockResult = { shipments: Shipment[] }

// Every error body from the backend has this shape (backend/app/api/errors.py).
export type ErrorBody = { error: string; detail: unknown }

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(`API error ${status}`)
    this.status = status
    this.body = body
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

// A readable one-line message for any failed call.
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as ErrorBody | null
    if (body && typeof body.detail === 'string') return body.detail
    if (body && Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg).join('; ')
    }
    return err.message
  }
  return 'The backend is unreachable. Is it running on :8000?'
}

export const api = {
  health: () => request<{ status: string }>('GET', '/health'),
  initCatalog: (products: ProductIn[]) => request<Product[]>('PUT', '/catalog', products),
  inventory: () => request<InventoryItem[]>('GET', '/inventory'),
  orders: () => request<Order[]>('GET', '/orders'),
  shipments: () => request<Shipment[]>('GET', '/shipments'),
  placeOrder: (order: OrderIn) => request<OrderResult>('POST', '/orders', order),
  restock: (lines: Line[]) => request<RestockResult>('POST', '/restocks', lines),
}
