# 快照管理

我接下来将会描述这个 mc 服务器管理系统中最重要，也是最提效的一个系统。也就是快照管理系统。

该快照管理系统使用 restic 作为快照管理工具。该工具可以为一个系统下面的所有文件夹或者指定文件夹创建快照。创建的快照将会以块的方式存储。文件将会被切块存储到另一个指定的文件夹中。该工具会使用 index 来管理一个快照下有哪些文件。

你应该编写可以实现以下功能的后端 api：

- 创建快照功能
- 列出所有快照功能
- 列出某个文件夹或者某个文件的可用快照

## 创建快照功能

创建快照使用 `restic backup {path}` 指令。

如果不指定 server id，也不指定 path，那么将会备份整个服务器目录。
如果指定了 server id，但是不指定 path，那么将会备份 id 对应的服务器目录。
如果指定了 server id，也指定了 path，那么实际的文件或者文件夹 path 将会是 {project_path}/data/{path}，注意不要用字符串拼接而是用 Path 操作。
review 一下 files.tsx，搞清除 files 这个端点的 path 带不带 data 目录。反正两边应该一致。

IMPORTANT: 经过上面推理之后得到的 path 一定要是**绝对路径**

## 列出所有快照功能

列出快照使用 `restic snapshots` 指令。

每一个快照会关联一个 paths 列表，即这个快照备份的路径列表。

如果不指定 server id 也不指定 path，那么上面那个指令的输出将不会被处理。
如果指定了 server id 但是没有指定 path，那么将使用 project_path 过滤所有快照的 path。如果一个快照的 path 中有任意一个为 project_path 的父目录或相等，那么就认为这个快照有效。过滤其他不含这个 path 的父目录的快照。
如果指定了 server id，也指定了 path，那么将使用 {project_path}/data/{path} 来进行过滤。过滤方式和上一条一样，也是检查所有快照 paths 列表是否为目标 path 的父目录或同一个目录。

`restic snapshots --json` 命令的输出范例如下（下面的代码经过格式化，实际上只会输出一行）：

```json
[
  {
    "time": "2025-09-05T19:22:52.534546972+08:00",
    "tree": "8d7bbec2be20f5e45ee406115a662cf79e0f7616db660d3da46c652431cbb3d8",
    "paths": ["/tmp/restic-test/backup"],
    "hostname": "Lazi-PC",
    "username": "root",
    "id": "7622b4a1095db23bd7444973fcc764573432362d83da177c650ed54e5ef7dfcc",
    "short_id": "7622b4a1"
  },
  {
    "time": "2025-09-05T19:23:14.662891678+08:00",
    "tree": "b79854c2ab5a637bfbb76e0704125c3f280e0b3503a97a8be9f7dcdebf3a64f1",
    "paths": ["/tmp/restic-test/dir/1"],
    "hostname": "Lazi-PC",
    "username": "root",
    "id": "6ad3ac3d6d0261f6e177c367e00feb28dedb1841b53886229b3e5d714beb6334",
    "short_id": "6ad3ac3d"
  },
  {
    "time": "2025-09-05T19:32:14.796667158+08:00",
    "tree": "4d1a15790e1e3b50390dd184c7dad4fa1194c4526798833d5dfcfb40ca2189d4",
    "paths": ["/tmp/restic-test/dir"],
    "hostname": "Lazi-PC",
    "username": "root",
    "program_version": "restic 0.18.0",
    "summary": {
      "backup_start": "2025-09-05T19:32:14.796667158+08:00",
      "backup_end": "2025-09-05T19:32:15.497296164+08:00",
      "files_new": 2,
      "files_changed": 0,
      "files_unmodified": 0,
      "dirs_new": 2,
      "dirs_changed": 0,
      "dirs_unmodified": 0,
      "data_blobs": 1,
      "tree_blobs": 3,
      "data_added": 1443,
      "data_added_packed": 1050,
      "total_files_processed": 2,
      "total_bytes_processed": 8
    },
    "id": "338e1b2ff89b342331e1f19f3b001a6eeea7c1e17beba6106b420b2d8f5706e9",
    "short_id": "338e1b2f"
  }
]
```

你应该创建一个 pydantic model 接收这个对象。我只希望这个 model 中有必要的字段，例如时间，paths，program_version, id 和 short_id。

## 还原快照功能

还原快照使用 `restic restore {snapshot_id} --target / --include {target_path} --delete`

target_path 的推导使用和上面一样的规则。

快照还原功能应该暴露两个 api，一个是快照还原预览， 一个是快照还原。
对于相同的请求参数，保证这两个请求对应的 restic 命令一致。

### 快照还原预览

快照还原预览功能会加上--dry-run -vv，用于预料当前操作会有什么后果

作为范例，当我运行这个命令：`restic restore latest --target / --include /tmp/restic-test/dir --dry-run -vv --delete --json`，其输出为：

```json
{"message_type":"verbose_status","action":"unchanged","item":"/tmp/restic-test/dir/1/1","size":4}
{"message_type":"verbose_status","action":"updated","item":"/tmp/restic-test/dir/222","size":4}
{"message_type":"verbose_status","action":"restored","item":"/tmp/restic-test/dir/1","size":0}
{"message_type":"verbose_status","action":"deleted","item":"/tmp/restic-test/dir/333","size":0}
{"message_type":"verbose_status","action":"restored","item":"/tmp/restic-test/dir","size":0}
{"message_type":"verbose_status","action":"restored","item":"/tmp/restic-test","size":0}
{"message_type":"verbose_status","action":"restored","item":"/tmp","size":0}
{"message_type":"summary","total_files":3,"files_restored":5,"files_skipped":1,"files_deleted":1,"total_bytes":4,"bytes_restored":4,"bytes_skipped":4}
```

其输出为多个 message object。应该是输出的每一行为一个 object。每一行作为一个 json 解析。我希望创建一个 pydantic model 接收每个 message，model 中只需要包含 message_type, action, item 和 size。

deleted 含义为当前版本有但是快照中没有，将会被删除。

只有 action 为 updated, deleted 或者 restored 并且 size 不为 0 才会被放到最终的返回列表中。

### 快照还原

快照还原功能不会带上--dry-run -vv。会真实地恢复快照。

---

运行 restic 指令时使用 exec_command。
应该传入配置的 uid 和 gid，以服务器用户运行 restic 指令。
在 env 字典中指定 RESTIC_REPOSITORY 和 RESTIC_PASSWORD

IMPORTANT: 所有的 restic 指令应该加上--json 以获得 json 格式的输出。

你需要注意的是， 快照 api 传入的目标文件或者文件夹是相对于服务器的目录，而不是操作系统目录。所以 api 中应该进行一下转换。

恢复快照前必须检查要恢复的文件夹或者文件是否有最近的快照（一分钟内的）。如果没有的话不允许恢复。同时在这里提供按钮快速为目标文件或者文件夹创建快照。

你应该为快照 api 创建非常完整的测试，涵盖各种 edge case。因为我们在操作文件，文件非常宝贵！
创建测试时在/tmp 目录下创建临时文件或文件夹。
因为快照功能和服务器挂钩，所以测试时应该修改 settings 或者 mock 一个 settings，指向 test 的服务器目录，而不是真正配置文件中的目录。
测试快照功能应该检查文件内容而不是单纯验证是否存在快照。

restic操作可以单独为一个module或者一个文件（取决于复杂度），这些操作里面不感知mc服务器。只有在endpoint函数里面才感知服务器环境并且计算真实path。

暂时不实现前端，现在只实现后端接口。
