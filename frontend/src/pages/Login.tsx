import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'
import { Button, ErrorBox, Field, inputCls } from '../components/ui'

const DEMO = [
  { username: 'sklad', password: 'sklad123', title: 'Кладовщик', name: 'Петров И. С.' },
  { username: 'tech', password: 'tech123', title: 'Технолог', name: 'Смирнова А. О.' },
  { username: 'boss', password: 'boss123', title: 'Руководитель', name: 'Кузнецов Д. П.' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(u = username, p = password, e?: FormEvent) {
    e?.preventDefault()
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

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl border border-wax-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-10 w-10" />
          <div>
            <h1 className="text-lg font-semibold">Свечная мастерская</h1>
            <p className="text-sm text-stone-500">Учёт склада, производства и ИИ-ассистент</p>
          </div>
        </div>
        <ErrorBox error={error} />
        <form onSubmit={(e) => submit(username, password, e)} className="space-y-3">
          <Field label="Логин">
            <input className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </Field>
          <Field label="Пароль">
            <input className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" disabled={busy} className="w-full">
            Войти
          </Button>
        </form>
        <div className="mt-6 border-t border-stone-100 pt-4">
          <div className="mb-2 text-xs font-medium text-stone-500">Демо-пользователи</div>
          <div className="grid gap-2">
            {DEMO.map((d) => (
              <button
                key={d.username}
                onClick={() => submit(d.username, d.password)}
                disabled={busy}
                className="flex items-center justify-between rounded-md border border-stone-200 px-3 py-2 text-left text-sm hover:bg-wax-50"
              >
                <span>
                  <span className="font-medium">{d.title}</span>
                  <span className="text-stone-500"> · {d.name}</span>
                </span>
                <span className="font-mono text-xs text-stone-400">{d.username}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
