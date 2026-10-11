import type { Product } from './api'

export const MAX_PACKAGE_MASS_G = 1800 // mirrors backend/app/domain/models.py

// Blood products come in families that an operator recognizes at a glance.
// The family only picks a color; nothing in the logic depends on it.
export type Family = 'rbc' | 'ffp' | 'plt' | 'cryo' | 'other'

export function family(product: Product | undefined): Family {
  const prefix = product?.product_name.split(' ')[0]
  switch (prefix) {
    case 'RBC':
      return 'rbc'
    case 'FFP':
      return 'ffp'
    case 'PLT':
      return 'plt'
    case 'CRYO':
      return 'cryo'
    default:
      return 'other'
  }
}

export type ProductMap = Map<number, Product>

export function productName(products: ProductMap, id: number): string {
  return products.get(id)?.product_name ?? `Product ${id}`
}
