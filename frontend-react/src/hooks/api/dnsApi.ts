import api from '@/utils/api'
import type {
  DNSRecord,
  DNSStatusResponse,
  DNSEnabledResponse,
  DNSUpdateResponse,
  RouterRoutes
} from '@/types/Dns'

export const updateDNS = async (): Promise<DNSUpdateResponse> => {
  const response = await api.post('/dns/update')
  return response.data
}

export const getDNSStatus = async (): Promise<DNSStatusResponse> => {
  const response = await api.get('/dns/status')
  return response.data
}

export const getDNSEnabled = async (): Promise<DNSEnabledResponse> => {
  const response = await api.get('/dns/enabled')
  return response.data
}

export const getDNSRecords = async (): Promise<DNSRecord[]> => {
  const response = await api.get('/dns/records')
  return response.data
}

export const getRouterRoutes = async (): Promise<RouterRoutes> => {
  const response = await api.get('/dns/routes')
  return response.data
}