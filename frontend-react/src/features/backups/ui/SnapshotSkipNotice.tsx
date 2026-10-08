export function SnapshotSkipNotice({ paths, count }: { paths: readonly string[]; count: number }) {
  if (!count) return null
  return <div className="space-y-1 text-sm text-muted-foreground">
    <p>将跳过 {count} 个忽略路径，保留其当前内容。</p>
    <ul className="max-h-32 overflow-y-auto font-mono break-all">
      {paths.map(path => <li key={path}>{path}</li>)}
    </ul>
    {count > paths.length && <p>仅列出前 {paths.length} 个路径。</p>}
  </div>
}
