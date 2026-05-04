export interface Insight {
  summary: string
  detail: string
  action: string
}

export interface Context {
  languages: string[]
  frameworks: string[]
  pattern: string
}

export interface Evidence {
  confidence: number
  confirmations: number
  first_observed: string | null
  last_confirmed: string | null
}

export interface Flag {
  reason: "stale" | "incorrect" | "duplicate"
  timestamp: string
  detail: string | null
  duplicate_of: string | null
}

export interface KnowledgeUnit {
  id: string
  version: number
  domains: string[]
  insight: Insight
  context: Context
  evidence: Evidence
  tier: string
  created_by: string
  superseded_by: string | null
  flags: Flag[]
}

export interface ReviewItem {
  knowledge_unit: KnowledgeUnit
  status: "pending" | "approved" | "rejected"
  reviewed_by: string | null
  reviewed_at: string | null
}

export interface ReviewQueueResponse {
  items: ReviewItem[]
  total: number
  offset: number
  limit: number
}

export type Selection = "approve" | "reject" | "skip" | null

export interface ReviewDecisionResponse {
  unit_id: string
  status: "approved" | "rejected"
  reviewed_by: string
  reviewed_at: string
}

export interface ActivityEvent {
  type: "proposed" | "approved" | "rejected"
  unit_id: string
  summary: string
  reviewed_by?: string
  timestamp: string
}

export interface DailyCount {
  date: string
  proposed: number
  approved: number
  rejected: number
}

export interface ReviewStatsResponse {
  counts: { pending: number; approved: number; rejected: number }
  domains: Record<string, number>
  confidence_distribution: Record<string, number>
  recent_activity: ActivityEvent[]
  trends: { daily: DailyCount[] }
}

export interface ApiKeyPublic {
  id: string
  name: string
  labels: string[]
  prefix: string
  ttl: string
  expires_at: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
  is_expired: boolean
  is_active: boolean
}

export interface CreatedApiKey extends ApiKeyPublic {
  token: string
}

export interface ApiKeysList {
  data: ApiKeyPublic[]
  count: number
}

export interface MessageResponse {
  message: string
}
