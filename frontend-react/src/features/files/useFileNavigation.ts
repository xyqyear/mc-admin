import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

export function useFileNavigation(onNavigate: () => void) {
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const currentPath = params.get('path') || '/'
  const searchQuery = params.get('q') || ''
  const useRegex = params.get('regex') === 'true'
  const [inputSearchTerm, setInputSearchTerm] = useState(searchQuery)
  useEffect(() => setInputSearchTerm(searchQuery), [searchQuery])

  const write = (path: string, query: string, regex: boolean, replace: boolean) => {
    const next = new URLSearchParams(location.search)
    if (path === '/') next.delete('path'); else next.set('path', path)
    if (query.trim()) next.set('q', query); else next.delete('q')
    if (regex) next.set('regex', 'true'); else next.delete('regex')
    const search = next.toString()
    navigate(`${location.pathname}${search ? `?${search}` : ''}`, { replace })
  }
  const updatePath = (path: string) => { write(path, '', false, false); onNavigate() }
  const updateSearch = (query: string, regex: boolean) => write(currentPath, query, regex, true)
  return {
    currentPath, searchQuery, useRegex, inputSearchTerm, updatePath,
    handleSearchChange: setInputSearchTerm,
    handleSearch: updateSearch,
    handleRegexChange: (regex: boolean) => updateSearch(inputSearchTerm, regex),
    handleSearchClear: () => { setInputSearchTerm(''); updateSearch('', false) },
    navigateSearchResult: (path: string, query = '', regex = false) => {
      write(path, query, regex, false); setInputSearchTerm(query); onNavigate()
    },
  }
}
