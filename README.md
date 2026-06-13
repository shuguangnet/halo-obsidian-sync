# Halo Obsidian Sync

将 Obsidian Markdown 笔记一键同步到 Halo 2.x 博客。支持单向同步、双向拉取、附件上传、标签/分类自动创建、冲突检测等高级功能。

## 功能

- ✅ **单篇/批量同步** Markdown 笔记
- ✅ **YAML Frontmatter 映射** — title, slug, tags, categories, excerpt
- ✅ **图片/附件自动上传** 至 Halo 附件库
- ✅ **增量更新** — 只同步变更的笔记
- ✅ **实时监听模式** — 文件修改后自动同步
- ✅ **标签/分类自动创建** — Halo 端不存在时自动创建
- ✅ **冲突检测** — Halo 端更新时提示，避免覆盖
- ✅ **双向同步** — 从 Halo 拉取文章到 Obsidian
- ✅ **同步日志 + 统计** — 记录每次操作，查看成功率
- ✅ **Obsidian 原生插件** — 无需离开 Obsidian

## 安装

```bash
cd halo-obsidian-sync
pip install -r requirements.txt

# 初始化配置
python halo_sync.py init
```

## 配置

运行 `init` 后会在 `~/.config/halo-obsidian-sync/config.json` 保存配置。
也可以通过环境变量设置：

```bash
export HALO_BASE_URL="https://blog.yourdomain.com"
export HALO_PAT_TOKEN="your...port OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

## 使用

### 子命令总览

```
python halo_sync.py init        # 初始化配置
python halo_sync.py sync        # 同步单篇
python halo_sync.py sync-all    # 批量同步
python halo_sync.py watch       # 实时监听
python halo_sync.py pull        # 从 Halo 拉取单篇
python halo_sync.py pull-all    # 从 Halo 拉取所有
python halo_sync.py log         # 查看同步日志
python halo_sync.py stats       # 查看同步统计
```

### 1. 笔记标记

在想同步的 Markdown 笔记最前面加上 YAML：

```yaml
---
title: "我的第一篇同步文章"
slug: "my-first-post"
tags:
  - 技术
  - 博客
categories:
  - 教程
halo_sync: true
halo_status: published
---

# 正文内容

这里是你的笔记内容...
```

### 2. 同步单篇

```bash
# 绝对路径
python halo_sync.py sync "/path/to/your/vault/笔记.md"

# 相对于 Vault 的路径
python halo_sync.py sync "笔记.md"

# 强制重新同步（忽略时间戳检查）
python halo_sync.py sync "笔记.md" --force
```

### 3. 批量同步

```bash
# 同步 Vault 中所有标记了 halo_sync: true 的笔记
python halo_sync.py sync-all

# 强制重新同步所有
python halo_sync.py sync-all --force
```

### 4. 实时监听

```bash
python halo_sync.py watch
```

修改笔记后自动检测并同步到 Halo。按 `Ctrl+C` 停止。

### 5. 双向同步 — 从 Halo 拉取

```bash
# 拉取单篇文章（需要知道 post_name，即 metadata.name）
python halo_sync.py pull "post-uuid-xxx"

# 保存到指定目录
python halo_sync.py pull "post-uuid-xxx" --dir "/path/to/save"

# 拉取所有文章
python halo_sync.py pull-all
```

### 6. 同步日志与统计

```bash
# 查看最近 30 条同步记录
python halo_sync.py log

# 查看最近 100 条
python halo_sync.py log -n 100

# 查看统计
python halo_sync.py stats
```

### 7. 集成到 Obsidian

安装「External Commands」插件（社区插件市场搜索即可），添加命令：

```bash
python /path/to/halo-obsidian-sync/halo_sync.py sync "{{file_path}}"
```

然后绑定你喜欢的快捷键（如 `Ctrl+Shift+H`）。

### 8. 原生 Obsidian 插件（推荐）

参见 `obsidian-plugin/README.md`。

## 数据映射关系

| Obsidian YAML | Halo 字段 | 说明 |
|--------------|-----------|------|
| `title` | `spec.title` | 文章标题 |
| `slug` | `spec.slug` | URL 路径标识，缺省文件名转 kebab-case |
| `tags` | `spec.tags` | 标签数组（不存在时自动创建） |
| `categories` | `spec.categories` | 分类数组（不存在时自动创建） |
| `excerpt` / `description` | `spec.excerpt.raw` | 摘要 |
| `halo_sync` | 本地标记 | 仅为 `true` 时才同步 |
| `halo_status` | 发布状态 | `published` 自动发布，默认为草稿 |
| `halo_post_name` | `metadata.name` | 已发布文章的 Halo 唯一 ID（自动填充） |
| `halo_last_sync` | 本地标记 | 上次同步时间（自动填充） |

## 图片处理

正文中的图片引用支持两种格式：

- **Obsidian WikiLink**: `![[image.png]]` —— 会自动定位并上传
- **标准 Markdown**: `![alt](attachments/image.png)` —— 相对路径也支持

上传后会自动替换为 Halo 附件库的永久链接。

## 冲突检测

当你在 Halo 后台修改了文章，而本地 Obsidian 笔记也被修改时，同步工具会检测到冲突并提示：

```
[⚠] conflict: Halo 端文章已更新，存在冲突。请使用 --force 强制覆盖或先拉取更新。
```

解决方案：
- 使用 `--force` 强制以本地版本覆盖 Halo
- 先运行 `python halo_sync.py pull <post_name>` 拉取最新版本，然后合并修改

## 目录结构

```
halo-obsidian-sync/
├── halo_sync.py          # CLI 入口
├── requirements.txt
├── src/
│   ├── config.py        # 配置管理
│   ├── halo_client.py   # Halo API 封装
│   ├── parser.py        # Markdown 解析
│   ├── sync_engine.py   # 同步引擎（含冲突检测、自动创建标签、双向同步）
│   └── sync_log.py    # 同步日志
├── tests/
│   └── fixtures/
│       └── sample_note.md
└── obsidian-plugin/    # 原生 Obsidian 插件
    ├── main.ts
    ├── main.js
    ├── manifest.json
    └── README.md
```

## Halo API 参考

- [Halo 官方文档](https://docs.halo.run/)
- [Halo 2.x API 测试台](https://api.halo.run/)

## License

MIT
