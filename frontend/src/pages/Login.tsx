import { Flame } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '@/auth'
import { Banner, Button, Field, Input, Tag } from '@/components/ui'

const DEMO = [
  { title: 'Кладовщик', name: 'Петров И. С.', login: 'sklad', password: 'sklad123' },
  { title: 'Технолог', name: 'Смирнова А. О.', login: 'tech', password: 'tech123' },
  { title: 'Руководитель', name: 'Кузнецов Д. П.', login: 'boss', password: 'boss123' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function signIn(u: string, p: string) {
    setBusy(true)
    setError(null)
    try {
      await login(u, p)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    signIn(username, password)
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-[380px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-accent text-white">
            <Flame className="size-[18px]" aria-hidden />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Свечная мастерская</h1>
            <p className="text-sm text-fg-muted">Учёт склада, производства и ИИ-ассистент</p>
          </div>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3.5 rounded-lg border border-border bg-surface p-6">
          {error && <Banner tone="error">{error}</Banner>}
          <Field label="Логин" htmlFor="login">
            <Input
              id="login"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Например, sklad"
            />
          </Field>
          <Field label="Пароль" htmlFor="password">
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary" fullWidth loading={busy} className="mt-1">
            Войти
          </Button>
        </form>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-2xs font-medium uppercase tracking-[0.06em] text-fg-muted">Демо-пользователи</span>
            <span className="text-xs text-fg-muted">вход в один клик</span>
          </div>
          <div className="flex flex-col gap-2">
            {DEMO.map((d) => (
              <button
                key={d.login}
                type="button"
                disabled={busy}
                onClick={() => signIn(d.login, d.password)}
                className="flex h-11 items-center gap-2.5 rounded border border-border bg-surface px-3 text-left transition-colors hover:border-border-strong hover:bg-subtle focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/25"
              >
                <span className="min-w-0 flex-1">
                  <b className="font-semibold">{d.title}</b> <span className="text-fg-muted">· {d.name}</span>
                </span>
                <Tag mono>{d.login}</Tag>
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
