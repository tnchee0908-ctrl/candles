import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  CardHeader,
  CardSkeleton,
  MaterialCode,
  PageHeader,
  Qty,
  Table,
  Td,
  Tr,
} from '@/components/ui'
import { formatQty } from '@/lib/format'
import type { Recipe } from '@/types'

const plural = (n: number) => (n % 10 === 1 && n % 100 !== 11 ? 'компонент' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'компонента' : 'компонентов')

/** 14 — Рецепты: карточки с нормами на 1 свечу. */
export default function RecipesPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [recipes, setRecipes] = useState<Recipe[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<Recipe[]>('/api/recipes')
      .then(setRecipes)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <Page>
      <PageHeader title="Рецепты" subtitle="Нормы расхода материалов на одну свечу." />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] items-start gap-4">
        {!recipes && !error && [0, 1, 2].map((i) => <CardSkeleton key={i} lines={6} />)}
        {recipes?.map((r) => (
          <Card key={r.id}>
            <CardHeader
              title={`Свеча «${r.name}»`}
              description={`${r.items.length} ${plural(r.items.length)}`}
              actions={
                can('manage_orders') && (
                  <Button variant="ghost" size="sm" icon={<Plus />} onClick={() => navigate(`/orders/new?recipe=${r.id}`)}>
                    Задание
                  </Button>
                )
              }
            />
            <Table>
              <tbody>
                {r.items.map((it) => (
                  <Tr key={it.material.id}>
                    <Td className="h-9">
                      {it.material.name}
                      <MaterialCode>{it.material.code}</MaterialCode>
                    </Td>
                    <Td align="right" className="h-9">
                      <Qty value={formatQty(it.qty_per_unit)} unit={it.material.unit} />
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
        ))}
      </div>
    </Page>
  )
}
