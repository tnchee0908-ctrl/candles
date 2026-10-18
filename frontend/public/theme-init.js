// Тема до отрисовки, чтобы не мелькала светлая (логика та же, что в src/theme.ts).
// Отдельным файлом, а не inline-скриптом: CSP разрешает только скрипты с нашего адреса.
try {
  var t = localStorage.getItem('candles_theme')
  var dark = t === 'dark' || (t !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
} catch (e) {}
