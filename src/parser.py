"""
Markdown 笔记解析器
支持:
  - 解析 YAML Frontmatter
  - 提取正文内容
  - 提取图片引用（WikiLink 和标准 Markdown 语法）
  - 回写 YAML 到文件
"""
import re
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    import frontmatter as fm_module
except ImportError:
    import yaml
    class fm_module:
        class Post:
            def __init__(self, metadata, content):
                self.metadata = metadata
                self.content = content
        @staticmethod
        def load(path: str):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    meta = yaml.safe_load(parts[1])
                    content = parts[2].strip()
                    return fm_module.Post(meta or {}, content)
            return fm_module.Post({}, text)


class NoteParser:
    """
    Obsidian 笔记解析器
    """

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()

    def parse(self, file_path: str) -> Dict[str, Any]:
        """
        解析单个 Markdown 文件，返回结构化数据
        返回格式:
        {
            "file_path": 绝对路径,
            "file_name": 文件名,
            "title": "...",
            "slug": "...",
            "tags": [...],
            "categories": [...],
            "excerpt": "...",
            "halo_sync": True/False,
            "halo_post_name": "..." | None,
            "halo_status": "draft" | "published" | None,
            "halo_last_sync": "2026-06-13T..." | None,
            "content": "Markdown 正文",
            "images": ["image.png", "attachments/shot.png"],
        }
        """
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        post = fm_module.load(str(file_path))
        meta = post.metadata
        content = post.content

        # 标题：优先使用 YAML title，缺省用文件名
        title = meta.get("title", file_path.stem)
        # slug：优先使用 YAML slug，缺省使用文件名转换为 kebab-case
        slug = meta.get("slug", self._to_slug(file_path.stem))
        # 标签
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        # 分类
        categories = meta.get("categories", [])
        if isinstance(categories, str):
            categories = [c.strip() for c in categories.split(",")]
        # 摘要
        excerpt = meta.get("excerpt", meta.get("description", ""))

        # Halo 同步相关字段
        halo_sync = meta.get("halo_sync", False)
        halo_post_name = meta.get("halo_post_name", None)
        halo_status = meta.get("halo_status", None)
        halo_last_sync = meta.get("halo_last_sync", None)

        # 提取文章中的图片引用
        images = self._extract_images(content)

        return {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "title": title,
            "slug": slug,
            "tags": tags,
            "categories": categories,
            "excerpt": excerpt,
            "halo_sync": halo_sync,
            "halo_post_name": halo_post_name,
            "halo_status": halo_status,
            "halo_last_sync": halo_last_sync,
            "content": content,
            "images": images,
        }

    def _to_slug(self, text: str) -> str:
        """将文件名转换为 kebab-case slug"""
        # 去除扩展名
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_-]", "-", text)
        text = re.sub(r"-+", "-", text).strip("-").lower()
        return text[:100]

    def _extract_images(self, content: str) -> List[str]:
        """
        提取 Markdown 中的图片引用
        支持:
          - Obsidian WikiLink: ![[image.png]]
          - 标准 Markdown: ![alt](path/to/image.png)
          - 绝对路径: ![alt](/vault/attachments/image.png)
        """
        images = []
        # 1. Obsidian WikiLink 语法: ![[image.png]]
        wiki_links = re.findall(r"!?\[\[([^\]]+)\]\]", content)
        for link in wiki_links:
            # 可能包含标签如 ![[image.png|300]]，去掉标签
            raw = link.split("|")[0].strip()
            if raw:
                images.append(raw)
        # 2. 标准 Markdown: ![alt](path)
        md_links = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content)
        for alt, path in md_links:
            path = path.strip()
            if path.startswith("http://") or path.startswith("https://"):
                continue  # 跳过网络图片
            images.append(path)
        return images

    def resolve_image_path(self, image_ref: str, note_dir: Path) -> Path:
        """
        将笔记中的图片引用转换为绝对路径
        优先策略:
          1. 相对于笔记所在目录
          2. 相对于 Vault 根目录
          3. 相对于 Vault/attachments/
        """
        candidates = [
            note_dir / image_ref,
            self.vault_path / image_ref,
            self.vault_path / "attachments" / image_ref,
            self.vault_path / "Images" / image_ref,
        ]
        for cand in candidates:
            if cand.exists():
                return cand.resolve()
        return None

    def update_note_metadata(self, file_path: str, meta_updates: Dict[str, Any]) -> None:
        """
        回写元数据到 Markdown 文件
        保留正文内容不变
        """
        file_path = Path(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # 使用 python-frontmatter 可以简单的方式重写
        try:
            import frontmatter as fm
            post = fm.load(str(file_path))
            for k, v in meta_updates.items():
                post.metadata[k] = v
            with open(file_path, "w", encoding="utf-8") as f:
                fm.dump(post, f)
        except Exception:
            # 降级方案：手动操作
            self._manual_update_metadata(file_path, raw, meta_updates)

    def _manual_update_metadata(self, file_path: Path, raw_text: str, updates: Dict[str, Any]):
        """手动更新 YAML frontmatter，不依赖第三方库"""
        import yaml
        if raw_text.startswith("---"):
            parts = raw_text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta.update(updates)
                new_front = yaml.dump(meta, allow_unicode=True, sort_keys=False)
                new_text = f"---\n{new_front}---\n{parts[2].strip()}\n"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_text)
                return
        # 如果没有 frontmatter，创建新的
        import yaml
        new_front = yaml.dump(updates, allow_unicode=True, sort_keys=False)
        new_text = f"---\n{new_front}---\n\n{raw_text.strip()}\n"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    def build_post_body(self, note: Dict[str, Any], visible: str = "PUBLIC") -> Dict[str, Any]:
        """
        将解析后的笔记数据构建为 Halo Post 对象
        """
        content = note["content"]
        title = note["title"] or note["file_name"]
        slug = note["slug"]
        tags = note["tags"]
        categories = note["categories"]
        excerpt = note["excerpt"]

        post = {
            "spec": {
                "title": title,
                "slug": slug,
                "content": content,
                "visible": visible,
            },
            "metadata": {
                "name": "",  # 等待创建后返回
            },
        }

        if tags:
            post["spec"]["tags"] = tags
        if categories:
            post["spec"]["categories"] = categories
        if excerpt:
            post["spec"]["excerpt"] = {
                "autoGenerate": False,
                "raw": excerpt,
            }

        return post
