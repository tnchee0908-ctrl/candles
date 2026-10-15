import { Compass } from 'lucide-react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { AppShell, Page } from './components/layout/AppShell'
import { Button, EmptyState } from './components/ui'
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
import SettingsPage from './pages/Settings'
import StockPage from './pages/Stock'

function NotFound() {
  const navigate = useNavigate()
  return (
    <Page>
      <EmptyState
        icon={<Compass />}
        title="Страница не найдена"
        description="Возможно, ссылка устарела."
        action={
          <Button size="sm" onClick={() => navigate('/batches')}>
            К реестру партий
          </Button>
        }
      />
    </Page>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <LoginPage />
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/batches" replace />} />
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
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
