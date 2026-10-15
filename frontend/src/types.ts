export type Light = 'green' | 'yellow' | 'red'

export interface User {
  id: number
  username: string
  full_name: string
  role: string
  role_title: string
  permissions: string[]
}

export interface Material {
  id: number
  code: string
  name: string
  unit: string
}

export interface Recipe {
  id: number
  name: string
  items: { material: Material; qty_per_unit: string }[]
}

export interface BatchRow {
  id: number
  number: string
  received_date: string
  material_code: string
  material: string
  unit: string
  supplier: string
  qty: string
  remaining_qty: string
  reserved_qty: string
  free_qty: string
  price: string
  currency: string
  rate: string
  rate_date: string
  unit_cost_rub: string
  status: 'on_check' | 'accepted' | 'rejected'
  status_title: string
  comment: string | null
}

export interface Page<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface AuditEntry {
  id: number
  at: string
  user_full_name: string
  entity_type: string
  entity_id: number
  entity_label: string | null
  action: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  via_assistant: boolean
}

export interface Movement {
  order_id: number
  order_number: string
  qty: string
  at: string | null
}

export interface BatchCard {
  batch: BatchRow
  receipt_number: string
  reservations: Movement[]
  consumptions: Movement[]
  history: AuditEntry[]
}

export interface OrderRow {
  id: number
  number: string
  product: string
  recipe_id: number
  qty: number
  planned_date: string
  workshop: number
  status: 'draft' | 'planned' | 'in_progress' | 'completed' | 'cancelled'
  status_title: string
  light: Light
}

export interface Component {
  material_id: number
  material_code: string
  material: string
  unit: string
  required_qty: string
  reserved_qty: string
  missing_qty: string
  actual_qty: string | null
  light: Light
}

export interface ReservationRow {
  batch_id: number
  batch_number: string
  material_id: number
  qty: string
  received_date: string
}

export interface MarkingAttempt {
  attempt_no: number
  at: string
  status_code: number | null
  error: string | null
  duration_ms: number
}

export interface Marking {
  id: number
  order_id: number
  order_number: string | null
  status: 'pending' | 'sent' | 'failed'
  attempts: number
  next_attempt_at: string | null
  last_error: string | null
  external_id: string | null
  sent_at: string | null
  idempotency_key: string
  attempt_log: MarkingAttempt[]
}

export interface OrderCard extends OrderRow {
  comment: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  components: Component[]
  reservations: ReservationRow[]
  consumptions: ReservationRow[]
  history: AuditEntry[]
  marking: Marking | null
}

export interface PreviewRow {
  material_code: string
  material: string
  unit: string
  required: string
  free_now: string
  will_reserve: string
  shortage: string
}

export interface StockRow {
  material_code: string
  material: string
  unit: string
  on_hand: string
  reserved: string
  free: string
  awaiting_inspection: string
  batches_with_stock: number
}

export interface ChatFile {
  id: number
  filename: string
  mime: string
}

export interface ToolCallInfo {
  name: string
  arguments: unknown
  ok: boolean
  summary: string
}

export interface CodeRun {
  code: string
  logs: string
  error: boolean
}

export interface ActionPreview {
  title: string
  recipe: string
  qty: number
  planned_date: string
  workshop: number
  comment?: string | null
  components: PreviewRow[]
  has_shortage: boolean
}

export interface ChatAction {
  id: number
  kind: string
  status: 'pending' | 'confirmed' | 'rejected' | 'failed'
  preview: ActionPreview
  result?: { order_id?: number; order_number?: string; shortage?: string | null; error?: string } | null
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'interrupted' | 'error' | 'streaming'
  model: string | null
  tool_calls: ToolCallInfo[]
  code: CodeRun[]
  files: ChatFile[]
  actions: ChatAction[]
  error: string | null
  fallback_used?: boolean
  system_note?: boolean
  created_at?: string | null
  /** клиентское: какие инструменты сейчас выполняются */
  running_tools?: string[]
}

export interface Conversation {
  id: number
  title: string
  updated_at: string
}

export interface Fact {
  id: number
  text: string
  created_at: string
}
