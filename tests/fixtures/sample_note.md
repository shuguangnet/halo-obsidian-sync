---
title: Halo 同步测试笔记
slug: halo-sync-test-note
tags:
- 技术
- Obsidian
- Halo
categories:
- 教程
halo_sync: true
halo_status: published
excerpt: 这是一篇用于测试 Halo Obsidian Sync 工具的笔记
halo_post_name: batch-post-uuid
halo_last_sync: '2026-06-13T17:21:52.279932+00:00'
---
# 欢迎使用 Halo Obsidian Sync

这是一篇测试笔记，用于验证同步工具的正常运行。

## 功能特点

- **一键发布**：在 Obsidian 中写完笔记，命令行运行 `python halo_sync.py sync 本篇笔记.md`
- **增量更新**＜二次同步时只传递变更部分
- **图片自动上传**：正文中的 `![[image.png]]` 会自动上传至 Halo 附件库

## 代码示例

```python
# 同步单篇
python halo_sync.py sync "/path/to/note.md"

# 批量同步
python halo_sync.py sync-all

# 监听模式
python halo_sync.py watch
```

这篇笔记同步后，你的 YAML frontmatter 中会自动添加：

```yaml
halo_post_name: "xxx-uuid"
halo_status: published
halo_last_sync: "2026-06-13T17:00:00Z"
```

---

快去试试看吧！
