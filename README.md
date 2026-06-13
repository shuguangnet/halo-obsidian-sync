# Halo Obsidian Sync

将 Obsidian Markdown 笔记一键同步到 Halo 2.x 博客。

## 功能

- 单篇/批量同步 Markdown 笔记
- YAML Frontmatter 映射（title, slug, tags, categories, excerpt）
- 图片/附件自动上传至 Halo 附件库
- 增量更新（只同步变更的笔记）
- 实时监听模式（文件修改后自动同步）

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
export HALO_PAT_TOKEN="your-personal-access-token"
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

## 使用

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

### 5. 集成到 Obsidian

安装「External Commands」插件（社区插件市场搜索即可），添加命令：

```bash
python /path/to/halo-obsidian-sync/halo_sync.py sync "{{file_path}}"
```

然后绑定你喜欢的快捷键（如 `Ctrl+Shift+H`）。

## 数据映射关系

| Obsidian YAML | Halo 字段 | 说明 |
|--------------|-----------|------|
| `title` | `spec.title` | 文章标题 |
| `slug` | `spec.slug` | URL 路径标识，缺省文件名转 kebab-case |
| `tags` | `spec.tags` | 标签数组 |
| `categories` | `spec.categories` | 分类数组 |
| `excerpt` / `description` | `spec.excerpt.raw` | 摘要 |
| `halo_sync` | 本地标记 | 仅为 `true` 时才同步 |
| `halo_status` | 发布状态 | `published` 自动发布，默认为草稿 |
| `halo_post_name` | `metadata.name` | 已发布文章的 Halo 唯一 ID（自动填充） |

## 图片处理

正文中的图片引用支持两种格式：

- **Obsidian WikiLink**: `![[image.png]]` —— 会自动定位并上传
- **标准 Markdown**: `![alt](attachments/image.png)` —— 相对路径也支持

上传后会自动替换为 Halo 附件库的永久链接。

## 目录结构

```
halo-obsidian-sync/
├── halo_sync.py          # CLI 入口
├── requirements.txt
├── src/
│   ├── config.py        # 配置管理
│   ├── halo_client.py   # Halo API 封装
│   ├── parser.py        # Markdown 解析
│   └── sync_engine.py   # 同步引擎
└── tests/
    └── fixtures/
        └── sample_note.md
```

## Halo API 参考

- [Halo 官方文档](https://docs.halo.run/)
- [Halo 2.x API 测试台](https://api.halo.run/)

## License

MIT
