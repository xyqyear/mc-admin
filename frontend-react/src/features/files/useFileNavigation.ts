import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { fileNavigationHref } from './navigation'

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
    navigate(fileNavigationHref(location, path, query, regex), { replace })
  }
  const updatePath = (path: string) => { write(path, '', false, false); onNavigate() }
  const updateSearch = (query: string, regex: boolean) => write(currentPath, query, regex, true)
  return {
    currentPath, searchQuery, useRegex, inputSearchTerm, updatePath,
    getPathHref: (path: string) => fileNavigationHref(location, path),
    handleSearchChange: setInputSearchTerm,
    handleSearch: updateSearch,
    handleRegexChange: (regex: boolean) => updateSearch(inputSearchTerm, regex),
    handleSearchClear: () => { setInputSearchTerm(''); updateSearch('', false) },
    navigateSearchResult: (path: string, query = '', regex = false) => {
      write(path, query, regex, false); setInputSearchTerm(query); onNavigate()
    },
  }
}
