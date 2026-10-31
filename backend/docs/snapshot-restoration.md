# Common snapshot restoration and previews

`app.snapshots` owns file/world recovery acceptance, retained history, safety
evidence, rollback and preview lifetime. [Snapshots](snapshots.md) owns Restic,
scope mappings, exclusion semantics and snapshot notes. [World adapters](world-restore.md)
own chunk merging, layout and map rendering. Observable behavior is specified in
[snapshot recovery](../../openspec/specs/snapshot-recovery/spec.md).

## Acceptance, safety and rollback

Manual creation uses `POST /snapshots {scope, note?}`. File and world recovery use
`POST /snapshots/restorations {scope, source_snapshot_id}` and returns
`202 {task_id, restoration_id, skipped_paths}`. The task worker waits for its
resources, revalidates frozen identity/path/protection, creates and persists a
safety snapshot plus missing-path evidence, then applies the selected replacement.
History acceptance occurs after the journal reserves the task and before its worker
starts. Rejection, queued cancellation and failure before execution settle history.
`GET /snapshots/restorations` and its detail route project journal state; rollback
availability follows retained generations and actual repository references.

The shared `/tasks/events` stream carries every active journal-backed restoration
with its scope and target server generations, including global scopes. Acceptance
notifies after the restoration transaction commits, before worker registration.
The entry remains until the journal has settled and the live task has finished
finalization. Initial snapshots combine unpaginated database projections with
active manager identities and do not access Restic. Frontend discovery uses this index
instead of periodic active-restoration reads, retaining its guard when observation
is disconnected or has not obtained a successful snapshot.

`POST /snapshots/restorations/{id}/rollback` creates another recovery task and
records its parent. It saves current contents first, including edits made since
the original restore. Missing targets use an owned temporary absence marker when
no live target exists; a rollback removes only allowed selected paths and empty
ancestors that were absent, preserving protected descendants and later siblings.
File, server and global scopes apply current, source and retained-chain exclusions.
World scopes ignore all exclusion records, including those retained by older
restorations; their safety snapshots capture the full selection.
Versioned history retains selected logical paths, frozen execution mappings and
missing execution ancestors with their logical projections. A dangling internal
directory link can therefore restore its missing real directory; rollback removes
newly created empty real ancestors and preserves the link node. Accepted target
claims cover these ancestors, and scope/mapping evidence is checked after restart.

Every restore owns its target file scope. Whole-server/data targets and paths
intersecting known world roots additionally require stopped servers and maintenance
ownership, the server's `MAP_CACHE` scope and the concrete
`FILES(data/.mcmap/tiles)` cache path; ordinary configuration/plugin/file restores
remain available online.
A normal file restore can run beside world maintenance when their file scopes do
not overlap. Dry-run preview and reads do not acquire these leases. Running/busy
and path checks repeat after acquisition. Invalid unrelated server.properties
values do not prevent recovery: world-name lookup reads only level-name.

Closing observation of a recovery does not stop it. Explicit task cancellation
waits for owned processes and finite cleanup. A failed or cancelled restore touching
world data clears the affected server's derived tiles even before the first Restic
file event. Successful restoration invalidates reported terrain changes. Cache
cleanup uses captured server references, so restored project metadata cannot hide
the affected cache. Unknown writers retain artifacts and mark cache degradation;
cleanup errors remain failed operations with retained history and safety evidence.

Accepted manual tasks hold deletion admission and target references through task
finalization. Server removal checks these references before cancelling other tasks
and again while frozen/exclusive; completed history does not block repository
retention. A missing safety snapshot leaves its history readable with an explicit
unavailable reason. Ordinary file restoration remains available online.
Safely successful restoration journal entries retain their snapshot/history
reference values as resolved historical links, allowing ordinary journal retention.
Failed recovery, staging evidence and unconfirmed writers keep their protection;
the [journal retention rules](operations.md#durable-state) define those boundaries.

世界执行共享命令和历史，按完整选区处理，mcmap 仅承担区块合并。`preparation.py` 解析目标、实例、缺失范围与源保护，供恢复和预览共用。cron 通过 `SnapshotCommands.backup` 执行同一创建逻辑，不另建手动任务或重复历史；维护冲突记录 `skipped`。备份已完成但保留策略因活动引用被拒绝时，cron 明确记录已创建快照及跳过清理的原因。

## Source eligibility

`POST /snapshots/eligible` requires source coverage or documented absence for
the selected scope. Missing coverage rejects a candidate and fails explicit
restoration before safety capture or writes.

File scopes combine current and source protection, omit protected roots, and
return `skipped_paths` (up to 100) plus `skipped_count`. Their stop checks use
the effective roots, so an excluded world path does not prevent an otherwise
online file restore. File previews, execution and rollback retain the same protection.

World scopes check MCA/directory coverage and absence evidence without evaluating
exclusions or enumerating speculative MCC paths. Missing selected data inside a
covered root is restored as absent. Their shared response skip fields are empty.
A request reuses decisions for sources with the same roots and absence evidence;
IDs, order and notes remain specific to each snapshot. Processing yields between
sources and during large coverage checks. Disconnecting the request cancels and
joins its owned repository read without cancelling accepted recovery tasks.

## 预览与仓库维护任务

`POST /api/snapshots/previews` 接受相同的 `scope` 与完整 `source_snapshot_id`，返回 202 任务。`snapshots/previews.py` 负责准备、绑定与查询，`preview_sessions.py` 统一心跳、有效期和清理，`world/preview_rendering.py` 只处理地图临时副本及瓦片。预览不创建安全快照，不写入恢复历史或在线目标。

文件预览保存 JSONL 明细，`GET /previews/{id}/actions?cursor=...&limit=...` 每页最多 200 条；响应提供下一页位置，零字节文件和目录动作也保留在明细中。明细总量上限为 64 MiB，单行上限为 32 KiB。超过限制时任务失败并要求缩小范围，不把截断结果当作完整预览。任务结果只含计数、说明和至多 100 个忽略路径。

就绪结果可由 `GET /previews/{id}` 读取，`POST /previews/{id}/heartbeat` 延长有效期。`DELETE /previews/{id}` 返回清理任务，等待读取与渲染退出后才完成。准备中关闭观察不取消任务；显式停止使用通用任务取消接口。每台服务器最多一个活动预览，全局预览同时占用其捕获的服务器集合。重启后结果不可再应用；未知写入者的临时目录和阻断证据仍保留。

带 `preview_id` 恢复时，受理和实际写入前都核对源 ID、规范化范围、服务器代次和已观测目标版本；文件流程还核对当前排除规则。版本结合选中目标的文件元数据与相关路径的操作记录；普通在线文件不扫描整棵目录、不承诺外部程序的原子状态。范围外的文件写入不会使预览失效。直接恢复仍可用，安全快照始终捕获执行前的真实状态。

`GET /api/snapshots/usage`、`GET /locks` 为普通读取。`DELETE /{snapshot_id}` 和 `POST /unlock` 返回任务；仓库独占占用从受理保留至所属进程及收尾结束，期间拒绝新的快照依赖。清锁只移除 Restic 判断已失效的锁，不能强制移除活跃锁。

Preview TTL defaults to 30 minutes; the browser heartbeats ready sessions every
30 seconds. Dynamic values live in `snapshots.world_restore`, including
`preview_session_ttl_seconds`, `preview_janitor_interval_seconds` and
`preview_avg_region_bytes`. Preparation progress extends a building session;
ready results use heartbeat/TTL. Expired sessions cannot be revived. The manager
owns one active preview per captured server and cleanup waits for active users.

## History and active observation

`GET /snapshots/restorations/active?server_id=...` reads only the journal and restoration tables. It includes queued, running, cancelling and finalizing work, including global restores targeting the selected server. Offset/limit pagination is bounded to 200 rows per request. History supports `kind`, `status`, `entry_point` and server filters before pagination, and projects all captured server generations. A failed history repository check does not prevent active task observation.

Preview preparation records its session identity in the submitted worker context. Non-successful completion awaits session closure before publishing terminal task status, even if cancellation arrives after a ready result. Unknown writers still retain protected artifacts and block unsafe reuse.

## Implementation and verification

`commands.py` accepts tasks and owns safety/history hooks; `preparation.py`
captures target identity and source protection; `restoration_store.py` persists
evidence; `queries.py` projects journal-backed state. `previews.py` and
`preview_sessions.py` own binding, task preparation and lifetime. World adapters
receive these accepted identities rather than rediscovering the current server.

See [world recovery test ownership](testing.md#unified-world-recovery-regression-ownership),
[snapshot API coverage](../../e2e/docs/coverage/files.md) and
[world API coverage](../../e2e/docs/coverage/world.md) for behavior assertions.
The [frontend common snapshot UI](../../frontend-react/docs/snapshot-recovery.md)
owns observation and presentation; UI feedback never replaces backend validation.
