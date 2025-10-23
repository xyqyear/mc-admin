import * as dnsApi from '@/hooks/api/dnsApi'
import { queryKeys } from '@/utils/api'
import { useQuery } from '@tanstack/react-query'

/**
 * Query for DNS status including differences
 * Only enabled when DNS is enabled
 */
export const useDNSStatus = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.status(),
    queryFn: dnsApi.getDNSStatus,
    refetchInterval: enabled ? 60000 : false, // Only refresh if enabled
    staleTime: 60000, // Consider stale after 60 seconds
    enabled, // Only run query if DNS is enabled
  });
};

/**
 * Query for DNS enabled status
 */
export const useDNSEnabled = () => {
  return useQuery({
    queryKey: queryKeys.dns.enabled(),
    queryFn: dnsApi.getDNSEnabled,
    staleTime: 60000, // 1 minute - configuration changes are infrequent
  });
};

/**
 * Query for current DNS records
 * Only enabled when DNS is enabled
 */
export const useDNSRecords = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.records(),
    queryFn: dnsApi.getDNSRecords,
    refetchInterval: enabled ? 10000 : false, // Only refresh if enabled
    staleTime: 60000, // Consider stale after 60 seconds
    enabled, // Only run query if DNS is enabled
  });
};

/**
 * Query for current router routes
 * Only enabled when DNS is enabled
 */
export const useRouterRoutes = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.routes(),
    queryFn: dnsApi.getRouterRoutes,
    refetchInterval: enabled ? 10000 : false, // Only refresh if enabled
    staleTime: 60000, // Consider stale after 60 seconds
    enabled, // Only run query if DNS is enabled
  });
};
