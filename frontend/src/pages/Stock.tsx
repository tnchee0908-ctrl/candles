import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, PageHeader, Table, td, tdNum, th } from '../components/ui'
import { num } from '../format'
import type { StockRow } from '../types'

export default function StockPage() {
  const [rows, setRows] = useState<StockRow[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api<StockRow[]>('/api/stock').then(setRows).catch((e) => setError(e.message))
  }, [])
  return (
    <div className="max-w-5xl">
      <PageHeader title="Остатки материалов" subtitle="Только принятые партии. «Ждёт приёмки» — партии на проверке, их пока нельзя резервировать." />
      <ErrorBox error={error} />
      <div className="rounded-lg border border-stone-200 bg-white shadow-sm">
        <Table>
          <thead>
            <tr>
              <th className={th}>Материал</th>
              <th className={`${th} text-right`}>На складе</th>
              <th className={`${th} text-right`}>В резерве</th>
              <th className={`${th} text-right`}>Свободно</th>
              <th className={`${th} text-right`}>Ждёт приёмки</th>
              <th className={`${th} text-right`}>Партий</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.material_code} className="hover:bg-wax-50">
                <td className={td}>
                  <Link to={`/batches?material=${encodeURIComponent(r.material_code)}`} className="text-wax-700 hover:underline">
                    {r.material}
                  </Link>{' '}
                  <span className="text-xs text-stone-400">{r.material_code}</span>
                </td>
                <td className={tdNum}>
                  {num(r.on_hand)} <span className="text-stone-400">{r.unit}</span>
                </td>
                <td className={tdNum}>{num(r.reserved)}</td>
                <td className={`${tdNum} font-medium ${Number(r.free) <= 0 ? 'text-red-700' : ''}`}>{num(r.free)}</td>
                <td className={tdNum}>{Number(r.awaiting_inspection) > 0 ? num(r.awaiting_inspection) : '—'}</td>
                <td className={tdNum}>{r.batches_with_stock}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </div>
  )
}
