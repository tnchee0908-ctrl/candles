import { History, MessageSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '@/api'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Card,
  Dash,
  DocLink,
  EmptyState,
  PageHeader,
  Pagination,
  Select,
  Table,
  TableScroll,
  TableSkeleton,
  Tag,
  Td,
  Th,
  Tr,
} from '@/components/ui'
import { auditChanges, auditSummary } from '@/lib/audit'
import { formatDateTime, shortName } from '@/lib/format'
import type { AuditEntry, Page as PageData } from '@/types'

const ENTITY: Record<string, string> = { batch: 'Партия', order: 'Задание', material: 'Материал', recipe: 'Рецепт', memory: 'Память ассистента' }
const LINK: Record<string, string> = { batch: 'batches', order: 'orders' }

/** 16 — Журнал изменений: кто, когда, что было и что стало — человекочитаемо, без JSON. */
export default function AuditPage() {
  const [data, setData] = useState<PageData<AuditEntry> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [entity, setEntity] = useState('')
  const [onlyAssistant, setOnlyAssistant] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  useEffect(() => {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (entity) q.set('entity_type', entity)
    if (onlyAssistant) q.set('via_assistant', 'true')
    api<PageData<AuditEntry>>(`/api/audit?${q}`)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [entity, onlyAssistant, page, pageSize])

  return (
    <Page wide>
      <PageHeader
        title="Журнал изменений"
        subtitle="Кто, когда, что было и что стало — по всем партиям, заданиям и рецептам."
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="w-[180px]">
          <Select
            aria-label="Тип объекта"
            value={entity}
            onChange={(e) => {
              setEntity(e.target.value)
              setPage(1)
            }}
          >
            <option value="">Все объекты</option>
            <option value="batch">Партии</option>
            <option value="order">Задания</option>
            <option value="material">Материалы</option>
            <option value="recipe">Рецепты</option>
            <option value="memory">Память ассистента</option>
          </Select>
        </div>
        <label className="ml-1 inline-flex items-center gap-2 text-sm text-fg-label">
          <input
            type="checkbox"
            className="size-4 accent-accent"
            checked={onlyAssistant}
            onChange={(e) => {
              setOnlyAssistant(e.target.checked)
              setPage(1)
            }}
          />
          Только через ассистента
        </label>
      </div>
      <Card>
        <TableScroll>
          <Table fixed minWidth={1060}>
            <colgroup>
              <col className="w-[148px]" />
              <col className="w-[164px]" />
              <col className="w-[150px]" />
              <col className="w-[190px]" />
              <col />
              <col />
            </colgroup>
            <thead>
              <tr>
                <Th>Когда</Th>
                <Th>Кто</Th>
                <Th>Объект</Th>
                <Th>Действие</Th>
                <Th>Было</Th>
                <Th>Стало</Th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((e) => {
                const { before, after } = auditSummary(auditChanges(e))
                const link = LINK[e.entity_type]
                return (
                  <Tr key={e.id}>
                    <Td className="align-top leading-5 [&]:py-2.5">{formatDateTime(e.at)}</Td>
                    <Td wrap>
                      <span title={e.user_full_name}>{shortName(e.user_full_name)}</span>
                      {e.via_assistant && (
                        <div className="mt-1">
                          <Tag>
                            <MessageSquare aria-hidden />
                            через ассистента
                          </Tag>
                        </div>
                      )}
                    </Td>
                    <Td className="align-top [&]:py-2.5">
                      {ENTITY[e.entity_type] ?? e.entity_type}{' '}
                      {link ? <DocLink to={`/${link}/${e.entity_id}`}>{e.entity_label}</DocLink> : e.entity_label}
                    </Td>
                    <Td wrap>{e.action}</Td>
                    <Td wrap className="text-fg-secondary">
                      {before ?? <Dash />}
                    </Td>
                    <Td wrap>{after}</Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        </TableScroll>
        {!data && !error && <TableSkeleton rows={8} cols={6} />}
        {data && data.items.length === 0 && (
          <EmptyState icon={<History />} title="Записей нет" description="Под выбранные условия не подходит ни одно изменение." />
        )}
        <Pagination
          total={data?.total ?? 0}
          page={page}
          pageSize={pageSize}
          onPage={setPage}
          onPageSize={(s) => {
            setPageSize(s)
            setPage(1)
          }}
        />
      </Card>
    </Page>
  )
}
