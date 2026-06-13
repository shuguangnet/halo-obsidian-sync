"""
同步引擎 - 协调解析器与 Halo 客户端
核心流程:
  1. 解析 Obsidian 笔记
  2. 提取并上传附件
  3. 构建 Halo Post 对象
  4. 调用 API 发布/更新
  5. 回写状态到本地 YAML

扩展功能:
  - 标签/分类自动创建
  - 冲突检测
  - 双向同步（拉取）
  - 同步日志
"""
import re
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from .config import Config
    from .parser import NoteParser
    from .halo_client import HaloClient, HaloError
    from .sync_log import SyncLog
except ImportError:
    from config import Config
    from parser import NoteParser
    from halo_client import HaloClient, HaloError
    from sync_log import SyncLog


class SyncEngine:
    """
    Obsidian → Halo 同步引擎
    """

    def __init__(self, config: Config):
        self.config = config
        self.config.validate()
        self.parser = NoteParser(config.get("vault_path"))
        self.client = HaloClient(
            base_url=config.get("halo_base_url"),
            token=config.get("halo_pat_token"),
            timeout=config.get("request_timeout", 30),
            retry=config.get("retry_count", 3),
        )
        self.log = SyncLog()
        self._cached_tags: Optional[List[str]] = None
        self._cached_categories: Optional[List[str]] = None
        self._cache_time = 0

    def sync_note(self, file_path: str, force: bool = False) -> Dict[str, Any]:
        """
        同步单篇笔记

        Args:
            file_path: Markdown 文件路径
            force: 是否强制重新同步（忽略时间戳检查）
        
        Returns:
            {"status": "created" | "updated" | "skipped" | "error" | "conflict", "post_name": "...", "message": "..."}
        """
        try:
            note = self.parser.parse(file_path)
        except Exception as e:
            self.log.add({"status": "error", "file_path": file_path, "message": f"解析失败: {e}"})
            return {"status": "error", "post_name": None, "message": f"解析失败: {e}"}

        # 检查同步开关
        if not note.get("halo_sync"):
            return {"status": "skipped", "post_name": None, "message": "halo_sync 未设置为 true，跳过"}

        # 检查是否已同步过，且未变更
        if not force and note.get("halo_post_name") and note.get("halo_last_sync"):
            mtime = os.path.getmtime(file_path)
            last_sync = self._parse_iso(note["halo_last_sync"])
            if last_sync and mtime <= last_sync.timestamp():
                return {"status": "skipped", "post_name": note["halo_post_name"], "message": "文件未变更，跳过"}

        # 冲突检测：Halo 端是否比本地更新
        if not force and note.get("halo_post_name"):
            try:
                conflict = self._detect_conflict(note.get("halo_post_name"), note.get("halo_last_sync"))
                if conflict:
                    self.log.add({"status": "conflict", "file_path": file_path, "post_name": note.get("halo_post_name"), "message": "Halo 端文章已更新，存在冲突"})
                    return {"status": "conflict", "post_name": note.get("halo_post_name"), "message": "Halo 端文章已更新，存在冲突。请使用 --force 强制覆盖或先拉取更新。"}
            except Exception:
                pass  # 冲突检测失败时继续同步

        # 自动创建标签/分类
        try:
            self._ensure_tags_and_categories(note.get("tags", []), note.get("categories", []))
        except Exception as e:
            print(f"[警告] 标签/分类处理失败: {e}")

        # 处理附件（图片）
        try:
            content = self._process_attachments(note)
        except Exception as e:
            self.log.add({"status": "error", "file_path": file_path, "message": f"附件处理失败: {e}"})
            return {"status": "error", "post_name": note.get("halo_post_name"), "message": f"附件处理失败: {e}"}

        # 构建 Halo Post 对象
        note["content"] = content
        post_body = self.parser.build_post_body(
            note,
            visible=self.config.get("default_visible", "PUBLIC"),
        )

        # 判断是创建还是更新
        post_name = note.get("halo_post_name")
        try:
            if post_name:
                # 更新
                existing = self.client.get_post(post_name)
                if existing:
                    # 更新时需要合并现有 metadata
                    post_body["metadata"] = existing.get("metadata", {})
                    self.client.update_post(post_name, post_body)
                    # 发布
                    if note.get("halo_status") == "published":
                        self.client.publish_post(post_name)
                    status = "updated"
                else:
                    # 已经有 post_name 但服务端不存在，重新创建
                    post_body["metadata"] = {}
                    created = self.client.create_post(post_body)
                    post_name = created["metadata"]["name"]
                    if note.get("halo_status") == "published":
                        self.client.publish_post(post_name)
                    status = "created"
            else:
                # 新建
                post_body["metadata"] = {}
                created = self.client.create_post(post_body)
                post_name = created["metadata"]["name"]
                if note.get("halo_status") == "published":
                    self.client.publish_post(post_name)
                status = "created"
        except HaloError as e:
            self.log.add({"status": "error", "file_path": file_path, "post_name": post_name, "message": f"Halo API 错误: {e}"})
            return {"status": "error", "post_name": post_name, "message": f"Halo API 错误: {e}"}
        except Exception as e:
            self.log.add({"status": "error", "file_path": file_path, "post_name": post_name, "message": f"未知错误: {e}"})
            return {"status": "error", "post_name": post_name, "message": f"未知错误: {e}"}

        # 回写本地 YAML
        now = datetime.now(timezone.utc).isoformat()
        self.parser.update_note_metadata(file_path, {
            "halo_post_name": post_name,
            "halo_status": note.get("halo_status", "published"),
            "halo_last_sync": now,
        })

        self.log.add({"status": status, "file_path": file_path, "post_name": post_name, "message": f"{status}: {note['title']}"})
        return {"status": status, "post_name": post_name, "message": f"{status}: {note['title']}"}

    def sync_all(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        批量同步 Vault 中所有标记了 halo_sync: true 的笔记
        """
        vault_path = Path(self.config.get("vault_path"))
        results = []
        for md_file in vault_path.rglob("*.md"):
            # 跳过 .obsidian 目录
            if ".obsidian" in str(md_file):
                continue
            result = self.sync_note(str(md_file), force=force)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 双向同步 — 从 Halo 拉取
    # ------------------------------------------------------------------

    def pull_post(self, post_name: str, target_dir: str = None) -> Dict[str, Any]:
        """
        从 Halo 拉取单篇文章到 Obsidian

        Args:
            post_name: Halo 文章的 metadata.name
            target_dir: 保存目录，缺省使用 Vault 根目录
        
        Returns:
            {"status": "pulled" | "error", "file_path": "...", "message": "..."}
        """
        try:
            post = self.client.get_post(post_name)
            if not post:
                return {"status": "error", "file_path": None, "message": f"文章 {post_name} 不存在"}
        except Exception as e:
            return {"status": "error", "file_path": None, "message": f"获取文章失败: {e}"}

        spec = post.get("spec", {})
        meta = post.get("metadata", {})
        title = spec.get("title", "untitled")
        slug = spec.get("slug", post_name)
        content = spec.get("content", "")
        tags = spec.get("tags", [])
        categories = spec.get("categories", [])
        excerpt = spec.get("excerpt", {})
        excerpt_raw = excerpt.get("raw", "") if isinstance(excerpt, dict) else ""

        # 构建 YAML frontmatter
        yaml_lines = ["---"]
        yaml_lines.append(f'title: "{title}"')
        yaml_lines.append(f'slug: "{slug}"')
        if tags:
            yaml_lines.append("tags:")
            for t in tags:
                yaml_lines.append(f"  - {t}")
        if categories:
            yaml_lines.append("categories:")
            for c in categories:
                yaml_lines.append(f"  - {c}")
        if excerpt_raw:
            yaml_lines.append(f'excerpt: "{excerpt_raw}"')
        yaml_lines.append("halo_sync: true")
        yaml_lines.append("halo_status: published")
        yaml_lines.append(f'halo_post_name: "{post_name}"')
        yaml_lines.append(f'halo_last_sync: "{datetime.now(timezone.utc).isoformat()}"')
        yaml_lines.append("---")
        yaml_lines.append("")

        # Halo 的内容可能是 HTML 或 Markdown
        # 如果内容以 < 开头，提示用户可能需要转换
        if content.strip().startswith("<"):
            yaml_lines.append("> **提示**：此文章内容为 HTML 格式，建议使用线上工具转换为 Markdown。")
            yaml_lines.append("")

        yaml_lines.append(content)
        yaml_lines.append("")

        file_body = "\n".join(yaml_lines)

        # 确定保存路径
        if not target_dir:
            target_dir = self.config.get("vault_path")
        target_path = Path(target_dir) / f"{slug}.md"

        # 如果文件已存在，追加后缀
        counter = 1
        original_path = target_path
        while target_path.exists():
            target_path = original_path.parent / f"{slug}-{counter}.md"
            counter += 1

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(file_body)

        self.log.add({"status": "pulled", "file_path": str(target_path), "post_name": post_name, "message": f"拉取: {title}"})
        return {"status": "pulled", "file_path": str(target_path), "message": f"拉取: {title} → {target_path.name}"}

    def pull_all_posts(self, target_dir: str = None) -> List[Dict[str, Any]]:
        """
        拉取 Halo 中所有文章到 Obsidian
        """
        results = []
        page = 0
        size = 50
        while True:
            try:
                resp = self.client.list_posts(page, size)
                items = resp.get("items", [])
                if not items:
                    break
                for item in items:
                    post_name = item.get("metadata", {}).get("name")
                    if post_name:
                        result = self.pull_post(post_name, target_dir)
                        results.append(result)
                page += 1
                if len(items) < size:
                    break
            except Exception as e:
                results.append({"status": "error", "file_path": None, "message": f"列表获取失败: {e}"})
                break
        return results

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _detect_conflict(self, post_name: str, last_sync_str: str) -> bool:
        """
        检测冲突：Halo 端是否比本地更新
        """
        try:
            post = self.client.get_post(post_name)
            if not post:
                return False
            meta = post.get("metadata", {})
            # 使用 creationTimestamp 作为远程修改时间
            remote_time_str = meta.get("creationTimestamp")
            if not remote_time_str:
                return False
            remote_time = self._parse_iso(remote_time_str)
            local_time = self._parse_iso(last_sync_str)
            if remote_time and local_time:
                return remote_time > local_time
        except Exception:
            return False
        return False

    def _ensure_tags_and_categories(self, tags: List[str], categories: List[str]):
        """
        自动创建不存在的标签和分类
        """
        # 获取现有标签
        existing_tags = self._get_existing_tags()
        for tag in tags:
            if tag not in existing_tags:
                try:
                    self._create_tag(tag)
                    existing_tags.add(tag)
                except Exception as e:
                    print(f"[警告] 创建标签 '{tag}' 失败: {e}")

        # 获取现有分类
        existing_categories = self._get_existing_categories()
        for cat in categories:
            if cat not in existing_categories:
                try:
                    self._create_category(cat)
                    existing_categories.add(cat)
                except Exception as e:
                    print(f"[警告] 创建分类 '{cat}' 失败: {e}")

    def _get_existing_tags(self) -> set:
        """缓存现有标签"""
        now = datetime.now().timestamp()
        if self._cached_tags is not None and (now - self._cache_time) < 300:  # 5 分钟缓存
            return set(self._cached_tags)

        tags = set()
        try:
            resp = self.client.list_tags(0, 200)
            items = resp.get("items", [])
            for item in items:
                spec = item.get("spec", {})
                name = spec.get("displayName", spec.get("slug", ""))
                if name:
                    tags.add(name)
        except Exception:
            pass
        self._cached_tags = list(tags)
        self._cache_time = now
        return tags

    def _get_existing_categories(self) -> set:
        """缓存现有分类"""
        now = datetime.now().timestamp()
        if self._cached_categories is not None and (now - self._cache_time) < 300:
            return set(self._cached_categories)

        categories = set()
        try:
            resp = self.client.list_categories(0, 200)
            items = resp.get("items", [])
            for item in items:
                spec = item.get("spec", {})
                name = spec.get("displayName", spec.get("slug", ""))
                if name:
                    categories.add(name)
        except Exception:
            pass
        self._cached_categories = list(categories)
        self._cache_time = now
        return categories

    def _create_tag(self, tag_name: str):
        """创建标签"""
        slug = self._to_slug(tag_name)
        color = self._random_color()
        body = {
            "spec": {
                "displayName": tag_name,
                "slug": slug,
                "color": color,
            },
            "metadata": {},
        }
        self.client.create_tag(body)

    def _create_category(self, category_name: str):
        """创建分类"""
        slug = self._to_slug(category_name)
        body = {
            "spec": {
                "displayName": category_name,
                "slug": slug,
            },
            "metadata": {},
        }
        self.client.create_category(body)

    def _to_slug(self, text: str) -> str:
        """将文本转换为 kebab-case slug"""
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_-]", "-", text)
        text = re.sub(r"-+", "-", text).strip("-").lower()
        return text[:100]

    def _random_color(self) -> str:
        """生成随机颜色"""
        colors = [
            "#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#ffeaa7",
            "#dfe6e9", "#fd79a8", "#fdcb6e", "#6c5ce7", "#a29bfe",
            "#74b9ff", "#55efc4", "#ff7675", "#fab1a0", "#81ecec",
        ]
        return random.choice(colors)

    def _process_attachments(self, note: Dict[str, Any]) -> str:
        """
        处理笔记中的图片附件
        返回替换过附件 URL 的正文
        """
        content = note["content"]
        note_dir = Path(note["file_path"]).parent

        for img_ref in note.get("images", []):
            img_path = self.parser.resolve_image_path(img_ref, note_dir)
            if not img_path:
                continue

            # 上传到 Halo
            try:
                att = self.client.upload_attachment(str(img_path))
                permalink = self._extract_permalink(att)
                if permalink:
                    # 替换正文中的引用
                    content = self._replace_image_ref(content, img_ref, permalink)
            except Exception as e:
                print(f"[警告] 上传附件 {img_ref} 失败: {e}")

        return content

    def _replace_image_ref(self, content: str, old_ref: str, new_url: str) -> str:
        """将正文中的图片引用替换为 URL"""
        # 替换 WikiLink: ![[old_ref]]
        content = re.sub(
            rf"!?\[\[{re.escape(old_ref)}(\|[^\]]*)?\]\]",
            f"![{Path(old_ref).name}]({new_url})",
            content,
        )
        # 替换标准 Markdown: ![alt](old_ref)
        # 注意 old_ref 可能是相对路径，需要正则精确匹配
        content = re.sub(
            rf"!\[([^\]]*)\]\({re.escape(old_ref)}\)",
            f"![\1]({new_url})",
            content,
        )
        return content

    def _extract_permalink(self, attachment: Dict[str, Any]) -> Optional[str]:
        """从l Halo 附件返回体中提取永久链接"""
        # Halo 2.x 附件返回结构示例:
        # {"spec": {"displayName": "...", "permalink": "https://..."}, "metadata": {"name": "..."}}
        if not attachment:
            return None
        spec = attachment.get("spec", {})
        return spec.get("permalink", spec.get("url", None))

    def _parse_iso(self, s: str) -> Optional[datetime]:
        """解析 ISO 8601 时间字符串"""
        if not s:
            return None
        try:
            # 处理 Python 3.11+ 的字符串格式
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
