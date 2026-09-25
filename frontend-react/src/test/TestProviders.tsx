import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'

export function TestProviders({ client, children, route = '/' }: {
  client: QueryClient
  children: ReactNode
  route?: string
}) {
  return <QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
  </QueryClientProvider>
}
