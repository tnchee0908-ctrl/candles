import type { ReserveLevel } from '@/components/ui/ReserveDot'
import type { Light } from '@/types'

/** Светофор с сервера (green/yellow/red) → уровень резерва для <ReserveDot/>. */
export function reserveLevel(light: Light, status?: string): ReserveLevel {
  if (status === 'draft') return 'none_draft'
  if (light === 'green') return 'full'
  return light === 'yellow' ? 'partial' : 'none'
}

/** Уровень по количествам: нужно / доступно к резерву. */
export function levelByQty(need: number, available: number): ReserveLevel {
  if (available >= need) return 'full'
  return available > 0 ? 'partial' : 'none'
}
