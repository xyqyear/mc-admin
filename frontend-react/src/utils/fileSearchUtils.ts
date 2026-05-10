export interface MatchResult {
  isMatch: boolean
  highlightedText?: string
}

// Case-insensitive subsequence match: returns the indices of matched chars so
// the caller can highlight them in the original text.
export function matchSubsequence(filename: string, searchTerm: string): MatchResult {
  if (!searchTerm.trim()) {
    return { isMatch: true }
  }

  const lowerFilename = filename.toLowerCase()
  const lowerSearchTerm = searchTerm.toLowerCase()

  let filenameIndex = 0
  let searchIndex = 0
  const matchedIndices: number[] = []

  while (filenameIndex < filename.length && searchIndex < lowerSearchTerm.length) {
    if (lowerFilename[filenameIndex] === lowerSearchTerm[searchIndex]) {
      matchedIndices.push(filenameIndex)
      searchIndex++
    }
    filenameIndex++
  }

  const isMatch = searchIndex === lowerSearchTerm.length

  if (!isMatch) {
    return { isMatch: false }
  }

  const highlightedText = generateHighlightedText(filename, matchedIndices)

  return { isMatch: true, highlightedText }
}

export function matchRegex(filename: string, regexPattern: string): MatchResult {
  if (!regexPattern.trim()) {
    return { isMatch: true }
  }

  try {
    const regex = new RegExp(regexPattern, 'i')
    const matches = filename.match(regex)

    if (!matches) {
      return { isMatch: false }
    }

    const highlightedText = filename.replace(regex, (match) =>
      `<mark>${match}</mark>`
    )

    return { isMatch: true, highlightedText }
  } catch {
    // Malformed regex falls back to a plain subsequence search.
    return matchSubsequence(filename, regexPattern)
  }
}

function generateHighlightedText(text: string, matchedIndices: number[]): string {
  if (matchedIndices.length === 0) {
    return text
  }

  let result = ''
  let currentIndex = 0

  for (const matchIndex of matchedIndices) {
    result += text.slice(currentIndex, matchIndex)

    result += `<mark>${text[matchIndex]}</mark>`

    currentIndex = matchIndex + 1
  }

  result += text.slice(currentIndex)

  return result
}

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

export function isValidRegex(pattern: string): boolean {
  try {
    new RegExp(pattern)
    return true
  } catch {
    return false
  }
}