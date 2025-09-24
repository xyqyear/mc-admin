/**
 * File search utilities for subsequence matching and highlighting
 */

export interface MatchResult {
  isMatch: boolean
  highlightedText?: string
}

/**
 * Case-insensitive subsequence matching algorithm
 * @param filename The filename to search in
 * @param searchTerm The search term (subsequence)
 * @returns Match result with highlighting information
 */
export function matchSubsequence(filename: string, searchTerm: string): MatchResult {
  if (!searchTerm.trim()) {
    return { isMatch: true }
  }

  const lowerFilename = filename.toLowerCase()
  const lowerSearchTerm = searchTerm.toLowerCase()

  let filenameIndex = 0
  let searchIndex = 0
  const matchedIndices: number[] = []

  // Find subsequence matches
  while (filenameIndex < filename.length && searchIndex < lowerSearchTerm.length) {
    if (lowerFilename[filenameIndex] === lowerSearchTerm[searchIndex]) {
      matchedIndices.push(filenameIndex)
      searchIndex++
    }
    filenameIndex++
  }

  // Check if all characters were matched
  const isMatch = searchIndex === lowerSearchTerm.length

  if (!isMatch) {
    return { isMatch: false }
  }

  // Generate highlighted text
  const highlightedText = generateHighlightedText(filename, matchedIndices)

  return { isMatch: true, highlightedText }
}

/**
 * Regular expression matching
 * @param filename The filename to search in
 * @param regexPattern The regex pattern
 * @returns Match result with highlighting information
 */
export function matchRegex(filename: string, regexPattern: string): MatchResult {
  if (!regexPattern.trim()) {
    return { isMatch: true }
  }

  try {
    const regex = new RegExp(regexPattern, 'i') // Case insensitive
    const matches = filename.match(regex)

    if (!matches) {
      return { isMatch: false }
    }

    // Generate highlighted text by wrapping all matches
    const highlightedText = filename.replace(regex, (match) =>
      `<mark>${match}</mark>`
    )

    return { isMatch: true, highlightedText }
  } catch {
    // Invalid regex, treat as literal string search
    return matchSubsequence(filename, regexPattern)
  }
}

/**
 * Generate highlighted text with matched characters wrapped in <mark> tags
 * @param text The original text
 * @param matchedIndices Array of indices to highlight
 * @returns HTML string with highlighted characters
 */
function generateHighlightedText(text: string, matchedIndices: number[]): string {
  if (matchedIndices.length === 0) {
    return text
  }

  let result = ''
  let currentIndex = 0

  for (const matchIndex of matchedIndices) {
    // Add non-highlighted text before the match
    result += text.slice(currentIndex, matchIndex)

    // Add highlighted character
    result += `<mark>${text[matchIndex]}</mark>`

    currentIndex = matchIndex + 1
  }

  // Add remaining non-highlighted text
  result += text.slice(currentIndex)

  return result
}

/**
 * Search files based on search term and regex mode
 * @param files Array of file items to search
 * @param searchTerm Search query
 * @param useRegex Whether to use regex matching
 * @returns Filtered files with match results
 */
export function searchFiles<T extends { name: string }>(
  files: T[],
  searchTerm: string,
  useRegex: boolean = false
): Array<T & { matchResult?: MatchResult }> {
  if (!searchTerm.trim()) {
    return files
  }

  const matchFunction = useRegex ? matchRegex : matchSubsequence

  return files
    .map(file => {
      const matchResult = matchFunction(file.name, searchTerm)
      return { ...file, matchResult }
    })
    .filter(file => file.matchResult?.isMatch)
}

/**
 * Validate regex pattern
 * @param pattern The regex pattern to validate
 * @returns Whether the pattern is valid
 */
export function isValidRegex(pattern: string): boolean {
  try {
    new RegExp(pattern)
    return true
  } catch {
    return false
  }
}