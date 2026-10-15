import { num } from '../format'
import type { PreviewRow } from '../types'
import { LightDot, Table, td, tdNum, th } from './ui'

/** Что будет зарезервировано при планировании — общий вид для формы и для карточки действия ассистента. */
export default function PreviewTable({ rows }: { rows: PreviewRow[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <th className={th}></th>
          <th className={th}>Материал</th>
          <th className={`${th} text-right`}>Нужно</th>
          <th className={`${th} text-right`}>Свободно</th>
          <th className={`${th} text-right`}>Дефицит</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const shortage = Number(r.shortage)
          const light = shortage <= 0 ? 'green' : Number(r.will_reserve) > 0 ? 'yellow' : 'red'
          return (
            <tr key={r.material_code}>
              <td className={td}>
                <LightDot light={light} />
              </td>
              <td className={td}>{r.material}</td>
              <td className={tdNum}>
                {num(r.required)} {r.unit}
              </td>
              <td className={tdNum}>{num(r.free_now)}</td>
              <td className={`${tdNum} ${shortage > 0 ? 'font-medium text-red-700' : 'text-stone-400'}`}>
                {shortage > 0 ? `${num(r.shortage)} ${r.unit}` : '—'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </Table>
  )
}
