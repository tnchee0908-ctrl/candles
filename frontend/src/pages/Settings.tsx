import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import { Card, CardBody, CardHeader, KeyValueList, PageHeader } from '@/components/ui'
import { cn } from '@/lib/cn'
import { saveTheme, storedTheme, type ThemeChoice } from '@/theme'

const THEMES: { value: ThemeChoice; label: string; hint: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Светлая', hint: 'Для яркого освещения', icon: Sun },
  { value: 'dark', label: 'Тёмная', hint: 'Меньше нагрузки на глаза вечером', icon: Moon },
  { value: 'system', label: 'Как в системе', hint: 'Следует настройке Windows или macOS', icon: Monitor },
]

/** Настройки пользователя: оформление и сведения об учётной записи. */
export default function SettingsPage() {
  const { user } = useAuth()
  const [theme, setTheme] = useState<ThemeChoice>(storedTheme)

  const choose = (value: ThemeChoice) => {
    setTheme(value)
    saveTheme(value)
  }

  return (
    <Page narrow>
      <PageHeader title="Настройки" subtitle="Личные настройки — действуют только в этом браузере." />
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="Оформление" description="Тема интерфейса" />
          <CardBody>
            <div role="radiogroup" aria-label="Тема" className="grid gap-2 sm:grid-cols-3">
              {THEMES.map(({ value, label, hint, icon: Icon }) => {
                const active = theme === value
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => choose(value)}
                    className={cn(
                      'relative flex flex-col items-start gap-2 rounded-lg border px-3.5 py-3 text-left transition-colors',
                      'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/25',
                      active ? 'border-accent bg-accent-25' : 'border-border bg-surface hover:border-border-strong hover:bg-subtle',
                    )}
                  >
                    <Icon className={cn('size-[18px]', active ? 'text-accent' : 'text-fg-muted')} aria-hidden />
                    <span>
                      <span className="block font-medium">{label}</span>
                      <span className="block text-xs text-fg-muted">{hint}</span>
                    </span>
                    {active && <Check className="absolute right-3 top-3 size-4 text-accent" aria-hidden />}
                  </button>
                )
              })}
            </div>
          </CardBody>
        </Card>

        {user && (
          <Card>
            <CardHeader title="Учётная запись" />
            <CardBody className="pb-3 pt-1">
              <KeyValueList
                items={[
                  { label: 'ФИО', value: user.full_name },
                  { label: 'Роль', value: user.role_title },
                  { label: 'Логин', value: <span className="font-mono text-sm">{user.username}</span> },
                ]}
              />
            </CardBody>
          </Card>
        )}
      </div>
    </Page>
  )
}
