# Halo Obsidian Sync 插件

将 Obsidian Markdown 笔记一键同步到 Halo 2.x 博客的原生插件。

## 功能

- ✅ **单篇同步**：当前打开的笔记点击就发
- ✅ **批量同步**：一次同步 Vault 中所有标记的笔记
- ✅ **增量更新**：二次同步时只传递变更
- ✅ **图片自动上传**：正文中 `![[image.png]]` 自动上传至 Halo 图床
- ✅ **实时状态**：状态栏显示同步状态
- ✅ **右键同步**：文件列表右键菜单直接同步
- ✅ **命令面板**：`Ctrl+P` 搜索 "Halo Sync"

## 安装

### 方法一：手动安装（推荐）

1. 下载本插件的 [main.js](main.js) 和 [manifest.json](manifest.json)
2. 在 Obsidian 中打开设置 → 第三方插件 → 打开插件文件夹
3. 创建文件夹 `halo-obsidian-sync`
4. 将 `main.js` 和 `manifest.json` 复制到该文件夹
5. 重新加载 Obsidian ，在第三方插件中启用

### 方法二：BRAT

1. 安装 BRAT 插件
2. 添加仓库: `https://github.com/shuguangnet/halo-obsidian-sync`
3. 在第三方插件中启用

## 配置

启用插件后，进入设置面板：

| 项目 | 说明 |
|------|------|
| Halo 博客地址 | 你的 Halo 站点，如 `https://blog.example.com` |
| Personal Access Token | Halo 后台「个人中心 → 个人令牌」生成 |
| 默认可见性 | 文章发布后的默认可见性 |
| 自动发布 | 同步后是否立即发布，关闭则保存为草稿 |
| 显示状态栏 | 底部状态栏显示同步状态 |

配置完成后点击「测试连接」验证 API 可用性。

## 使用

### 笔记标记

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

### 同步方式

| 操作 | 方法 |
|------|------|
| 同步当前笔记 | `Ctrl+P` → "Halo Sync: 同步当前笔记到 Halo" |
| 强制重新同步 | `Ctrl+P` → "Halo Sync: 强制重新同步当前笔记到 Halo" |
| 批量同步 | `Ctrl+P` → "Halo Sync: 批量同步所有标记的笔记到 Halo" |
| 右键同步 | 文件列表右键 → 「同步到 Halo」 |
| 点击状态栏 | 点击底部状态栏 "📰 Halo" |

## 数据映射

| Obsidian YAML | Halo 字段 | 说明 |
|--------------|-----------|------|
| `title` | `spec.title` | 文章标题 |
| `slug` | `spec.slug` | URL 路径标识，缺省文件名转 kebab-case |
| `tags` | `spec.tags` | 标签数组 |
| `categories` | `spec.categories` | 分类数组 |
| `excerpt` / `description` | `spec.excerpt.raw` | 摘要 |
| `halo_sync` | 本地标记 | 仅为 `true` 时才同步 |
| `halo_status` | 发布状态 | `published` 自动发布，默认草稿 |
| `halo_post_name` | `metadata.name` | 已发布文章的 Halo 唯一 ID（自动填充） |
| `halo_last_sync` | 本地标记 | 上次同步时间（自动填充） |

## 图片处理

正文中的图片引用支持两种格式：

- **Obsidian WikiLink**: `![[image.png]]` —— 自动定位并上传
- **标准 Markdown**: `![alt](attachments/image.png)` —— 相对路径也支持

上传后会自动替换为 Halo 附件库的永久链接。

## 目录结构

```
obsidian-plugin/
├── manifest.json      ← 插件元数据
├── main.ts          ← TypeScript 源码
├── main.js          ← 编译出的插件文件（产物）
├── package.json
├── tsconfig.json
├── esbuild.config.mjs
└── README.md
```

## 开发

```bash
cd obsidian-plugin
npm install
npm run build    # 编译为 main.js
npm run dev      # 开发模式（自动监听变更）
```

## 与 Python CLI 的关系

本插件是独立实现的原生插件，无需安装 Python 环境。
同一仓库中的 `python/` 目录还提供了命令行版本（适合自动化脚本和 CI 场景）。

## License

MIT
