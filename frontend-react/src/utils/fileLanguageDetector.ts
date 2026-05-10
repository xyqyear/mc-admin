// Compatibility shim — real implementations live in @/config/fileEditingConfig.
import {
  detectFileLanguage as _detectFileLanguage,
  getLanguageEditorOptions as _getLanguageEditorOptions,
  type LanguageConfig,
} from "@/config/fileEditingConfig";

/** @deprecated Import from @/config/fileEditingConfig. */
export const detectFileLanguage = _detectFileLanguage;

/** @deprecated Import from @/config/fileEditingConfig. */
export const getLanguageEditorOptions = _getLanguageEditorOptions;

export type { LanguageConfig };
