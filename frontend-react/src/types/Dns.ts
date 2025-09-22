export interface DNSRecord {
  sub_domain: string
  value: string
  record_id: string | number
  record_type: string
  ttl: number
}

export interface DNSRecordDiff {
  records_to_add: DNSRecord[]
  records_to_remove: string[] // Record IDs
  records_to_update: DNSRecord[]
}

export interface RouterDiff {
  routes_to_add: Record<string, string>
  routes_to_remove: Record<string, string>
  routes_to_update: Record<string, Record<string, string>>
}

export interface DNSStatusResponse {
  initialized: boolean
  dns_diff: DNSRecordDiff | null
  router_diff: RouterDiff | null
  errors: string[]
}

export interface DNSEnabledResponse {
  enabled: boolean
}

export interface DNSUpdateResponse {
  success: boolean
  message: string
}

export type RouterRoutes = Record<string, string>