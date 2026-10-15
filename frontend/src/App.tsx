import type { ReactNode } from 'react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { Loading } from './components/ui'
import AssistantPage from './pages/Assistant'
import AuditPage from './pages/Audit'
import BatchCardPage from './pages/BatchCard'
import BatchesPage from './pages/Batches'
import LoginPage from './pages/Login'
import MarkingPage from './pages/Marking'
import MemoryPage from './pages/Memory'
import NewOrderPage from './pages/NewOrder'
import NewReceiptPage from './pages/NewReceipt'
import OrderCardPage from './pages/OrderCard'
import OrdersPage from './pages/Orders'
import RecipesPage from './pages/Recipes'
import StockPage from './pages/Stock'

interface NavItem {
  to: string
  label: string
  perm?: string
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Склад',
    items: [
      { to: '/batches', label: 'Реестр партий' },
      { to: '/stock', label: 'Остатки' },
      { to: '/receipts/new', label: 'Поступление', perm: 'create_receipt' },
    ],
  },
  {
    section: 'Производство',
    items: [
      { to: '/orders', label: 'Задания' },
      { to: '/recipes', label: 'Рецепты' },
      { to: '/marking', label: 'Маркировка', perm: 'view_marking' },
    ],
  },
  {
    section: 'Ассистент',
    items: [
      { to: '/assistant', label: 'Чат' },
      { to: '/memory', label: 'Память' },
    ],
  },
  { section: 'Контроль', items: [{ to: '/audit', label: 'Журнал изменений', perm: 'view_audit' }] },
]

function Layout({ children }: { children: ReactNode }) {
  const { user, logout, can } = useAuth()
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-wax-200 bg-white">
        <div className="flex items-center gap-2 px-4 py-4">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">Свечная мастерская</div>
            <div className="text-xs text-stone-500">учёт и ассистент</div>
          </div>
        </div>
        <nav className="flex-1 space-y-4 px-2 py-2">
          {NAV.map((group) => {
            const items = group.items.filter((i) => !i.perm || can(i.perm))
            if (!items.length) return null
            return (
              <div key={group.section}>
                <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-stone-400">
                  {group.section}
                </div>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `block rounded-md px-2 py-1.5 text-sm ${isActive ? 'bg-wax-100 font-medium text-wax-900' : 'text-stone-700 hover:bg-stone-100'}`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <div className="border-t border-stone-100 px-4 py-3 text-xs">
          <div className="font-medium text-stone-800">{user?.full_name}</div>
          <div className="text-stone-500">{user?.role_title}</div>
          <button onClick={logout} className="mt-2 text-wax-700 hover:underline">
            Выйти
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
    </div>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  if (!user) return <LoginPage />
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/batches" replace />} />
        <Route path="/batches" element={<BatchesPage />} />
        <Route path="/batches/:id" element={<BatchCardPage />} />
        <Route path="/stock" element={<StockPage />} />
        <Route path="/receipts/new" element={<NewReceiptPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/new" element={<NewOrderPage />} />
        <Route path="/orders/:id" element={<OrderCardPage />} />
        <Route path="/recipes" element={<RecipesPage />} />
        <Route path="/marking" element={<MarkingPage />} />
        <Route path="/assistant/:conversationId?" element={<AssistantPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="*" element={<div className="text-stone-500">Страница не найдена.</div>} />
      </Routes>
    </Layout>
  )
}
