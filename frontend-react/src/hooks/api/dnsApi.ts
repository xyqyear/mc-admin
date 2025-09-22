import api from '@/utils/api'
import type {
  DNSRecord,
  DNSStatusResponse,
  DNSEnabledResponse,
  DNSUpdateResponse,
  RouterRoutes
} from '@/types/Dns'

/**
 * Trigger a DNS and MC Router update
 */
export const updateDNS = async (): Promise<DNSUpdateResponse> => {
  const response = await api.post('/dns/update')
  return response.data
}

/**
 * Get DNS manager status including current differences between expected and actual state
 */
export const getDNSStatus = async (): Promise<DNSStatusResponse> => {
  const response = await api.get('/dns/status')
  return response.data
}

/**
 * Get DNS manager enabled status from configuration
 */
export const getDNSEnabled = async (): Promise<DNSEnabledResponse> => {
  const response = await api.get('/dns/enabled')
  return response.data
}

/**
 * Get current DNS records from DNS provider
 */
export const getDNSRecords = async (): Promise<DNSRecord[]> => {
  const response = await api.get('/dns/records')
  return response.data
}

/**
 * Get current routes from MC Router
 */
export const getRouterRoutes = async (): Promise<RouterRoutes> => {
  const response = await api.get('/dns/routes')
  return response.data
}