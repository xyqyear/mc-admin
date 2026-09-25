import ts from 'typescript'

const entryFiles = new Set(['api', 'auth', 'authCommands', 'contracts', 'lifecycleContracts', 'queries', 'commands', 'operationResources'])
const featureEntries = {
  health: ['useSelfCheckHealth'],
  servers: ['presentation'],
  tasks: ['downloads'],
}
const screenEntries = new Set([
  'archives/ArchiveManagementScreen', 'backups/SnapshotsScreen',
  'configuration/ConfigurationScreen', 'dns/DnsManagementScreen',
  'files/FileBrowserScreen', 'health/SelfCheckScreen',
  'players/PlayerManagementScreen', 'schedules/CronManagementScreen',
  'servers/ServerConsoleScreen', 'servers/ServerDetailScreen', 'servers/ServerNewScreen',
  'settings/DynamicConfigScreen', 'templates/DefaultVariablesScreen',
  'templates/TemplateEditScreen', 'templates/TemplateListScreen',
  'users/LoginScreen', 'users/UserManagementScreen',
  'world/prune/ChunkPruneScreen', 'world/restore/WorldRestoreScreen',
])
const legacyRoots = new Set(['hooks', 'components', 'stores', 'types', 'utils', 'lib', 'config'])

export function importBoundaryViolation(from, to) {
  const source = from.split('/')
  const target = to.replace(/\.(tsx?|jsx?)$/, '').split('/')
  if (legacyRoots.has(target[0])) return 'deleted compatibility layer'
  if (source[0] === 'shared' && ['features', 'app', 'pages'].includes(target[0])) return 'shared must not depend on application features'
  if (source[0] === 'features' && ['app', 'pages'].includes(target[0])) return 'features must not depend on application composition'
  if (source[0] === 'features' && target[0] === 'features') {
    const layer = source[2]?.replace(/\.ts$/, '')
    if (['contracts', 'api', 'queries'].includes(layer) && ['ui', 'components'].includes(target[2])) return `${layer} must not import UI`
    if (layer === 'contracts' && !['contracts', 'lifecycleContracts', 'generated'].includes(target[2])) return 'contracts must not depend on behavior'
    if (source[1] === target[1]) return null
  }
  if (target[0] === 'features' && (source[0] !== 'features' || source[1] !== target[1])) {
    const entry = target.slice(2).join('/')
    if (entryFiles.has(entry) || entry.startsWith('ui/') || featureEntries[target[1]]?.includes(entry)) return null
    if (['app', 'pages'].includes(source[0]) || from === 'App.tsx') {
      if (screenEntries.has(target.slice(1).join('/'))) return null
    }
    return 'feature implementation is private; use its public contract, query, command or UI entry'
  }
  return null
}

export function moduleReferences(filename, source) {
  const parsed = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true)
  const references = []
  function visit(node) {
    let module
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) module = node.moduleSpecifier
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || node.expression.getText(parsed) === 'require')) module = node.arguments[0]
    if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) module = node.argument.literal
    if (module && ts.isStringLiteral(module)) references.push({ name: module.text, line: parsed.getLineAndCharacterOfPosition(module.getStart(parsed)).line + 1 })
    ts.forEachChild(node, visit)
  }
  visit(parsed)
  return references
}
