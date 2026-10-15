/** Склейка className без зависимостей (аналог clsx). */
export function cn(...parts: Array<string | number | boolean | null | undefined>): string {
  return parts.filter((p) => typeof p === 'string' && p.length > 0).join(' ');
}
