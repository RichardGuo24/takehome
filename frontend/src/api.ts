// Hand-written types mirroring the backend's Pydantic schemas (backend/app/api/schemas.py).
// There are only a handful, so codegen isn't worth the setup. Keep the two in sync.

export type ProductIn = { product_id: number; product_name: string; mass_g: number }
export type Line = { product_id: number; quantity: number }
export type OrderIn = { order_id: number; requested: Line[] }

// Response types are added alongside the endpoints that return them.

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

export const api = {
  health: () => request<{ status: string }>('GET', '/health'),
}
