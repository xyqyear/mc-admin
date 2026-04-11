// Re-export shadcn-themed RJSF form
// Direct consumers will be cleaned up during page migrations
import { withTheme } from '@rjsf/core'
import { Theme as ShadcnTheme } from '@rjsf/shadcn'

const ThemedForm = withTheme(ShadcnTheme)

export default ThemedForm
