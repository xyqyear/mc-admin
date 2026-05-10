import * as dnsApi from '@/hooks/api/dnsApi'
import { queryKeys } from '@/utils/api'
import { useQuery } from '@tanstack/react-query'

export const useDNSStatus = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.status(),
    queryFn: dnsApi.getDNSStatus,
    refetchInterval: enabled ? 60000 : false,
    staleTime: 60000,
    enabled,
  });
};

export const useDNSEnabled = () => {
  return useQuery({
    queryKey: queryKeys.dns.enabled(),
    queryFn: dnsApi.getDNSEnabled,
    staleTime: 60000,
  });
};

export const useDNSRecords = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.records(),
    queryFn: dnsApi.getDNSRecords,
    refetchInterval: enabled ? 10000 : false,
    staleTime: 60000,
    enabled,
  });
};

export const useRouterRoutes = (enabled: boolean = true) => {
  return useQuery({
    queryKey: queryKeys.dns.routes(),
    queryFn: dnsApi.getRouterRoutes,
    refetchInterval: enabled ? 10000 : false,
    staleTime: 60000,
    enabled,
  });
};
