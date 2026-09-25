// Compatibility shim — real implementations live in @/features/files/editingConfig.
import {
  detectFileLanguage as _detectFileLanguage,
  getLanguageEditorOptions as _getLanguageEditorOptions,
  type LanguageConfig,
} from "@/features/files/editingConfig";

/** @deprecated Import from @/features/files/editingConfig. */
export const detectFileLanguage = _detectFileLanguage;

/** @deprecated Import from @/features/files/editingConfig. */
export const getLanguageEditorOptions = _getLanguageEditorOptions;

export type { LanguageConfig };
