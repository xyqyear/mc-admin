/**
 * File Editing Configuration
 * 
 * Centralized configuration for file editing features including:
 * - Language detection and Monaco Editor configuration
 * - File override warnings for Docker Compose conflicts
 * - Editable file type definitions
 */

// ========================================================================================
// Types and Interfaces
// ========================================================================================

/**
 * Language configuration for Monaco Editor
 */
export interface LanguageConfig {
  language: string
  supportsValidation: boolean
  description: string
}

/**
 * Configuration for files that can be overridden by compose settings
 */
export interface ComposeOverrideWarning {
  shouldWarn: boolean
  title: string
  message: string
  linkText: string
  severity: 'warning' | 'info' | 'error'
}

/**
 * File editability configuration
 */
export interface FileEditabilityConfig {
  isEditable: boolean
  maxSizeBytes?: number
  requiresWarning?: boolean
}

// ========================================================================================
// Language Mapping Configuration
// ========================================================================================

/**
 * Language mapping based on file extensions
 * Prioritizes configuration files with syntax validation support
 */
export const LANGUAGE_MAP: Record<string, LanguageConfig> = {
  // JSON variants
  '.json': { language: 'json', supportsValidation: true, description: 'JSON' },
  '.json5': { language: 'json', supportsValidation: true, description: 'JSON5' },
  '.jsonc': { language: 'json', supportsValidation: true, description: 'JSON with Comments' },
  
  // YAML variants
  '.yaml': { language: 'yaml', supportsValidation: true, description: 'YAML' },
  '.yml': { language: 'yaml', supportsValidation: true, description: 'YAML' },
  
  // TOML (fallback to ini since Monaco doesn't have native TOML support)
  '.toml': { language: 'ini', supportsValidation: false, description: 'TOML' },
  
  // Configuration files (INI-style)
  '.ini': { language: 'ini', supportsValidation: false, description: 'INI Configuration' },
  '.cfg': { language: 'ini', supportsValidation: false, description: 'Configuration File' },
  '.conf': { language: 'ini', supportsValidation: false, description: 'Configuration File' },
  '.config': { language: 'ini', supportsValidation: false, description: 'Configuration File' },
  
  // Properties files
  '.properties': { language: 'properties', supportsValidation: false, description: 'Properties File' },
  '.env': { language: 'properties', supportsValidation: false, description: 'Environment Variables' },
  
  // Programming languages
  '.js': { language: 'javascript', supportsValidation: true, description: 'JavaScript' },
  '.mjs': { language: 'javascript', supportsValidation: true, description: 'JavaScript Module' },
  '.cjs': { language: 'javascript', supportsValidation: true, description: 'CommonJS Module' },
  '.ts': { language: 'typescript', supportsValidation: true, description: 'TypeScript' },
  '.tsx': { language: 'typescript', supportsValidation: true, description: 'TypeScript React' },
  '.jsx': { language: 'javascript', supportsValidation: true, description: 'JavaScript React' },
  
  // Markup languages
  '.html': { language: 'html', supportsValidation: true, description: 'HTML' },
  '.htm': { language: 'html', supportsValidation: true, description: 'HTML' },
  '.xml': { language: 'xml', supportsValidation: true, description: 'XML' },
  '.svg': { language: 'xml', supportsValidation: true, description: 'SVG' },
  
  // Stylesheet languages
  '.css': { language: 'css', supportsValidation: true, description: 'CSS' },
  '.scss': { language: 'scss', supportsValidation: true, description: 'Sass/SCSS' },
  '.sass': { language: 'sass', supportsValidation: true, description: 'Sass' },
  '.less': { language: 'less', supportsValidation: true, description: 'Less' },
  
  // Shell scripts
  '.sh': { language: 'shell', supportsValidation: false, description: 'Shell Script' },
  '.bash': { language: 'shell', supportsValidation: false, description: 'Bash Script' },
  '.zsh': { language: 'shell', supportsValidation: false, description: 'Zsh Script' },
  '.fish': { language: 'shell', supportsValidation: false, description: 'Fish Script' },
  
  // Markdown
  '.md': { language: 'markdown', supportsValidation: false, description: 'Markdown' },
  '.markdown': { language: 'markdown', supportsValidation: false, description: 'Markdown' },
  
  // Log files
  '.log': { language: 'log', supportsValidation: false, description: 'Log File' },
  
  // SQL
  '.sql': { language: 'sql', supportsValidation: true, description: 'SQL' },
  
  // Python
  '.py': { language: 'python', supportsValidation: true, description: 'Python' },
  '.pyw': { language: 'python', supportsValidation: true, description: 'Python' },
  
  // Java
  '.java': { language: 'java', supportsValidation: true, description: 'Java' },
  '.class': { language: 'java', supportsValidation: true, description: 'Java' },
  
  // C/C++
  '.c': { language: 'c', supportsValidation: true, description: 'C' },
  '.cpp': { language: 'cpp', supportsValidation: true, description: 'C++' },
  '.cxx': { language: 'cpp', supportsValidation: true, description: 'C++' },
  '.cc': { language: 'cpp', supportsValidation: true, description: 'C++' },
  '.h': { language: 'c', supportsValidation: true, description: 'C Header' },
  '.hpp': { language: 'cpp', supportsValidation: true, description: 'C++ Header' },
  
  // Go
  '.go': { language: 'go', supportsValidation: true, description: 'Go' },
  
  // Rust
  '.rs': { language: 'rust', supportsValidation: true, description: 'Rust' },
  
  // PHP
  '.php': { language: 'php', supportsValidation: true, description: 'PHP' },
  '.phtml': { language: 'php', supportsValidation: true, description: 'PHP' },
  
  // Ruby
  '.rb': { language: 'ruby', supportsValidation: true, description: 'Ruby' },
  '.gemfile': { language: 'ruby', supportsValidation: true, description: 'Ruby Gemfile' },
  
  // Other text formats
  '.txt': { language: 'text', supportsValidation: false, description: 'Plain Text' },
  '.text': { language: 'text', supportsValidation: false, description: 'Plain Text' }
}

// ========================================================================================
// File Editability Configuration
// ========================================================================================

/**
 * File editability configuration based on backend server implementation
 * These extensions match the backend's _is_editable_file() function in servers.py
 * 
 * Backend editable extensions (from app/routers/servers.py:147-157):
 * .yml, .yaml, .properties, .json, .toml, .conf, .cfg, .txt, .log
 */
export const BACKEND_EDITABLE_EXTENSIONS = new Set([
  '.yml',
  '.yaml', 
  '.properties',
  '.json',
  '.toml',
  '.conf',
  '.cfg',
  '.txt',
  '.log'
])

/**
 * Extended file editability map for frontend-only features
 * Note: The backend determines actual editability, this is for UI enhancements
 */
export const FILE_EDITABILITY_MAP: Record<string, FileEditabilityConfig> = {
  // Backend-supported editable files
  '.yml': { isEditable: true },
  '.yaml': { isEditable: true },
  '.properties': { isEditable: true, requiresWarning: true },
  '.json': { isEditable: true },
  '.toml': { isEditable: true },
  '.conf': { isEditable: true },
  '.cfg': { isEditable: true },
  '.txt': { isEditable: true },
  '.log': { isEditable: true, maxSizeBytes: 10 * 1024 * 1024 }, // 10MB limit
  
  // Additional text formats that might be editable (frontend suggestion)
  '.json5': { isEditable: true },
  '.jsonc': { isEditable: true },
  '.ini': { isEditable: true },
  '.config': { isEditable: true },
  '.env': { isEditable: true },
  '.md': { isEditable: true },
  '.markdown': { isEditable: true },
  
  // Binary files (definitely not editable)
  '.jar': { isEditable: false },
  '.zip': { isEditable: false },
  '.png': { isEditable: false },
  '.jpg': { isEditable: false },
  '.jpeg': { isEditable: false },
  '.gif': { isEditable: false },
  '.pdf': { isEditable: false },
  '.db': { isEditable: false },
  '.sqlite': { isEditable: false },
  '.class': { isEditable: false }
}

// ========================================================================================
// Compose Override Warning Configuration
// ========================================================================================

/**
 * Configuration for files that can be overridden by Docker Compose settings
 */
export const COMPOSE_OVERRIDE_WARNINGS: Record<string, ComposeOverrideWarning> = {
  'server.properties': {
    shouldWarn: true,
    title: '配置文件覆盖提醒',
    message: '此文件的部分设置可能会被 Docker Compose 配置覆盖。为确保配置生效，建议通过 Compose 配置页面进行修改。',
    linkText: '前往 Compose 配置',
    severity: 'warning'
  },
  
  'user_jvm_args.txt': {
    shouldWarn: true,
    title: 'JVM 参数覆盖提醒', 
    message: '此文件中的 JVM 参数可能会被 Docker Compose 环境变量覆盖。建议通过 Compose 配置页面设置 JVM 参数以确保生效。',
    linkText: '前往 Compose 配置',
    severity: 'warning'
  },
  
  'eula.txt': {
    shouldWarn: true,
    title: 'EULA 配置提醒',
    message: '此文件的 EULA 同意状态通常由 Docker Compose 环境变量控制。建议通过 Compose 配置页面进行管理。',
    linkText: '前往 Compose 配置', 
    severity: 'info'
  }
}

// ========================================================================================
// Monaco Editor Options Configuration
// ========================================================================================

/**
 * Gets Monaco Editor configuration options for a specific language
 */
export function getLanguageEditorOptions(language: string): any {
  const baseOptions = {
    formatOnPaste: true,
    formatOnType: false,
    quickSuggestions: false,
    folding: true,
    foldingStrategy: 'indentation',
    showFoldingControls: 'mouseover',
    bracketPairColorization: {
      enabled: true
    },
    guides: {
      indentation: true,
      bracketPairs: true
    }
  }

  switch (language) {
    case 'json':
    case 'json5':
    case 'jsonc':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full',
        bracketPairColorization: {
          enabled: true
        }
      }
      
    case 'yaml':
    case 'yml':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full',
        wordBasedSuggestions: false
      }
      
    case 'toml':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full'
      }
      
    case 'ini':
    case 'properties':
      return {
        ...baseOptions,
        tabSize: 4,
        insertSpaces: true,
        wordWrap: 'on'
      }
      
    case 'javascript':
    case 'typescript':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full',
        suggestOnTriggerCharacters: true
      }
      
    case 'html':
    case 'xml':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full',
        autoClosingTags: true
      }
      
    case 'css':
    case 'scss':
    case 'less':
      return {
        ...baseOptions,
        formatOnType: true,
        quickSuggestions: true,
        tabSize: 2,
        insertSpaces: true,
        autoIndent: 'full'
      }
      
    default:
      return baseOptions
  }
}

// ========================================================================================
// Utility Functions
// ========================================================================================

/**
 * Detects the Monaco Editor language based on file name or path
 * 
 * @param fileName - The name of the file (can include path)
 * @returns Language configuration with language ID and validation support info
 */
export function detectFileLanguage(fileName: string): LanguageConfig {
  if (!fileName) {
    return { language: 'text', supportsValidation: false, description: 'Plain Text' }
  }
  
  // Normalize the filename
  const normalizedName = fileName.toLowerCase()
  
  // Check for file extensions
  const dotIndex = normalizedName.lastIndexOf('.')
  if (dotIndex > -1) {
    const extension = normalizedName.substring(dotIndex)
    if (LANGUAGE_MAP[extension]) {
      return LANGUAGE_MAP[extension]
    }
  }
  
  // Default to plain text
  return { language: 'text', supportsValidation: false, description: 'Plain Text' }
}


/**
 * Checks if a file can be overridden by compose settings and returns warning info
 * 
 * @param fileName - The name of the file (can include path)
 * @returns Warning configuration if the file can be overridden
 */
export function getComposeOverrideWarning(fileName: string): ComposeOverrideWarning {
  if (!fileName) {
    return { shouldWarn: false, title: '', message: '', linkText: '', severity: 'info' }
  }

  const baseName = fileName.split('/').pop()?.toLowerCase() || ''
  
  if (COMPOSE_OVERRIDE_WARNINGS[baseName]) {
    return COMPOSE_OVERRIDE_WARNINGS[baseName]
  }
  
  return { shouldWarn: false, title: '', message: '', linkText: '', severity: 'info' }
}

/**
 * Checks if a file extension is editable according to backend rules
 * This matches the backend's _is_editable_file() function logic
 * 
 * @param fileName - The name of the file (can include path)
 * @returns True if the backend considers this file editable
 */
export function isBackendEditableFile(fileName: string): boolean {
  if (!fileName) {
    return false
  }
  
  const normalizedName = fileName.toLowerCase()
  const dotIndex = normalizedName.lastIndexOf('.')
  
  if (dotIndex > -1) {
    const extension = normalizedName.substring(dotIndex)
    return BACKEND_EDITABLE_EXTENSIONS.has(extension)
  }
  
  return false
}

/**
 * Gets file editability configuration for frontend features
 * Note: Actual editability is determined by backend's is_editable field
 * 
 * @param fileName - The name of the file (can include path)
 * @returns File editability configuration for frontend features
 */
export function getFileEditability(fileName: string): FileEditabilityConfig {
  if (!fileName) {
    return { isEditable: false }
  }
  
  const normalizedName = fileName.toLowerCase()
  const dotIndex = normalizedName.lastIndexOf('.')
  
  if (dotIndex > -1) {
    const extension = normalizedName.substring(dotIndex)
    if (FILE_EDITABILITY_MAP[extension]) {
      return FILE_EDITABILITY_MAP[extension]
    }
  }
  
  // Default: assume not editable if not explicitly configured
  return { isEditable: false }
}