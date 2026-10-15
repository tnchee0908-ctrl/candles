import type { Config } from 'tailwindcss';

/**
 * Свечная мастерская — дизайн-токены.
 * Все цвета берутся из CSS-переменных (src/styles/tokens.css) в формате "R G B",
 * поэтому работают модификаторы прозрачности (bg-accent/20), а тёмную тему
 * можно добавить позже, переопределив переменные под [data-theme="dark"].
 */
const c = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: c('canvas'), // фон приложения
        surface: c('surface'), // карточки, таблицы, сайдбар
        subtle: c('subtle'), // шапка таблицы, hover строки
        muted: c('muted'), // нейтральные заливки, disabled
        hover: c('hover'), // hover ghost-кнопок
        border: {
          DEFAULT: c('border'),
          strong: c('border-strong'), // рамка полей и secondary-кнопок
          soft: c('border-soft'), // разделители внутри карточек
          hover: c('border-hover'),
        },
        fg: {
          DEFAULT: c('fg'),
          label: c('fg-label'),
          secondary: c('fg-secondary'),
          muted: c('fg-muted'),
          subtle: c('fg-subtle'), // единицы измерения, коды
          faint: c('fg-faint'), // placeholder, disabled
        },
        accent: {
          DEFAULT: c('accent'),
          hover: c('accent-hover'),
          ink: c('accent-ink'), // текст на accent-50
          25: c('accent-25'),
          50: c('accent-50'),
          200: c('accent-200'),
        },
        success: { bg: c('success-bg'), fg: c('success-fg'), dot: c('success-dot'), border: c('success-border') },
        warning: { bg: c('warning-bg'), fg: c('warning-fg'), dot: c('warning-dot'), border: c('warning-border'), icon: c('warning-icon') },
        danger: { bg: c('danger-bg'), fg: c('danger-fg'), dot: c('danger-dot'), border: c('danger-border'), ink: c('danger-ink') },
        info: { bg: c('info-bg'), fg: c('info-fg'), dot: c('info-dot') },
        progress: { bg: c('progress-bg'), fg: c('progress-fg'), dot: c('progress-dot') },
        neutral: { bg: c('neutral-bg'), fg: c('neutral-fg'), dot: c('neutral-dot') },
        code: { bg: c('code-bg'), fg: c('code-fg') },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['11px', { lineHeight: '16px' }], // overline, группы меню
        xs: ['12px', { lineHeight: '16px' }], // caption
        sm: ['13px', { lineHeight: '18px' }], // small, sm-контролы
        base: ['14px', { lineHeight: '20px' }], // body
        md: ['16px', { lineHeight: '24px' }], // заголовок секции
        lg: ['18px', { lineHeight: '24px' }],
        xl: ['22px', { lineHeight: '28px', letterSpacing: '-0.01em' }], // заголовок страницы
        '2xl': ['28px', { lineHeight: '36px', letterSpacing: '-0.01em' }], // метрика
      },
      borderRadius: {
        sm: '4px', // бейдж, чип
        DEFAULT: '6px', // кнопка, поле, баннер
        md: '6px',
        lg: '8px', // карточка, поповер
      },
      boxShadow: {
        popover: '0 8px 24px rgb(28 25 23 / 0.10), 0 2px 6px rgb(28 25 23 / 0.06)',
        tooltip: '0 4px 12px rgb(28 25 23 / 0.16)',
        segment: '0 1px 2px rgb(28 25 23 / 0.08)',
      },
      height: { row: '40px', control: '36px', 'control-sm': '30px' },
      width: { sidebar: '240px', chatlist: '260px' },
      maxWidth: { content: '1200px', chat: '820px' },
      keyframes: {
        blink: { '0%, 80%, 100%': { opacity: '0.3' }, '40%': { opacity: '1' } },
      },
      animation: { blink: 'blink 1.2s ease-in-out infinite' },
    },
  },
  plugins: [],
} satisfies Config;
