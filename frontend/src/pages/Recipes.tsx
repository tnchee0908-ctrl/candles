import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, ErrorBox, PageHeader } from '../components/ui'
import { num } from '../format'
import type { Recipe } from '../types'

export default function RecipesPage() {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api<Recipe[]>('/api/recipes').then(setRecipes).catch((e) => setError(e.message))
  }, [])
  return (
    <div className="max-w-5xl">
      <PageHeader title="Рецепты" subtitle="Нормы расхода материалов на 1 свечу" />
      <ErrorBox error={error} />
      <div className="grid gap-4 md:grid-cols-3">
        {recipes.map((r) => (
          <Card key={r.id} title={`Свеча «${r.name}»`}>
            <ul className="space-y-1 text-sm">
              {r.items.map((i) => (
                <li key={i.material.id} className="flex justify-between gap-2">
                  <span>{i.material.name}</span>
                  <span className="tabular-nums text-stone-600">
                    {num(i.qty_per_unit)} {i.material.unit}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  )
}
