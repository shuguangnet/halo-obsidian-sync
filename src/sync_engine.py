"""
同步引擎 - 协调解析器与 Halo 客户端
核心流程:
  1. 解析 Obsidian 笔记
  2. 提取并上传附件
  3. 构建 Halo Post 对象
  4. 调用 API 发布/更新
  5. 回写状态到本地 YAML
"""
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from .config import Config
    from .parser import NoteParser
    from .halo_client import HaloClient, HaloError
except ImportError:
    from config import Config
    from parser import NoteParser
    from halo_client import HaloClient, HaloError


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
        self._synced = []
        self._errors = []

    def sync_note(self, file_path: str, force: bool = False) -> Dict[str, Any]:
        """
        同步单篇笔记

        Args:
            file_path: Markdown 文件路径
            force: 是否强制重新同步（忽略时间戳检查）
        
        Returns:
            {"status": "created" | "updated" | "skipped" | "error", "post_name": "...", "message": "..."}
        """
        try:
            note = self.parser.parse(file_path)
        except Exception as e:
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

        # 处理附件（图片）
        try:
            content = self._process_attachments(note)
        except Exception as e:
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
            return {"status": "error", "post_name": post_name, "message": f"Halo API 错误: {e}"}
        except Exception as e:
            return {"status": "error", "post_name": post_name, "message": f"未知错误: {e}"}

        # 回写本地 YAML
        now = datetime.now(timezone.utc).isoformat()
        self.parser.update_note_metadata(file_path, {
            "halo_post_name": post_name,
            "halo_status": note.get("halo_status", "published"),
            "halo_last_sync": now,
        })

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
