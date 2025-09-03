/**
 * File Language Detector Utility
 * 
 * Legacy file - functionality has been moved to @/config/fileEditingConfig.ts
 * This file is kept for backward compatibility.
 */

import { 
  detectFileLanguage as _detectFileLanguage,
  getLanguageEditorOptions as _getLanguageEditorOptions,
  type LanguageConfig
} from '@/config/fileEditingConfig'


/**
 * @deprecated Use detectFileLanguage from @/config/fileEditingConfig instead
 */
export const detectFileLanguage = _detectFileLanguage

/**
 * @deprecated Use getLanguageEditorOptions from @/config/fileEditingConfig instead
 */
export const getLanguageEditorOptions = _getLanguageEditorOptions

// Re-export type for backward compatibility
export type { LanguageConfig }

