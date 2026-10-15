/**
 * Тема оформления. Выбор хранится в браузере пользователя (это личная настройка, а не данные системы).
 * «Как в системе» следует настройке ОС и переключается на лету.
 * Первичная установка до отрисовки — в index.html, чтобы не было вспышки светлой темы.
 */

export type ThemeChoice = 'light' | 'dark' | 'system'

const KEY = 'candles_theme'
const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

export function storedTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const dark = choice === 'dark' || (choice === 'system' && darkQuery().matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

export function saveTheme(choice: ThemeChoice): void {
  try {
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch {
    /* приватный режим — тема применится, но не запомнится */
  }
  applyTheme(choice)
}

/** Следить за сменой темы в ОС, пока выбрано «Как в системе». */
export function watchSystemTheme(): () => void {
  const query = darkQuery()
  const onChange = () => {
    if (storedTheme() === 'system') applyTheme('system')
  }
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}
