"""
配置模块 - 管理 Halo Obsidian Sync 的用户配置
配置文件位于: ~/.config/halo-obsidian-sync/config.json
"""
import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "halo-obsidian-sync" / "config.json"

DEFAULT_CONFIG = {
    "halo_base_url": "",
    "halo_pat_token": "",
    "vault_path": "",
    "attachment_base_path": "attachments",
    "sync_tag": "halo_sync",
    "default_visible": "PUBLIC",
    "retry_count": 3,
    "request_timeout": 30,
}


class Config:
    """管理配置的类，支持从l环境变量或文件读取"""

    def __init__(self, path: str = None):
        self._path = Path(path) if path else DEFAULT_CONFIG_PATH
        self._data = {}
        self.load()

    def load(self):
        """加载配置文件，不存在则使用默认值"""
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = dict(DEFAULT_CONFIG)
        # 环境变量覆盖
        self._data["halo_base_url"] = os.getenv("HALO_BASE_URL", self._data.get("halo_base_url", ""))
        self._data["halo_pat_token"] = os.getenv("HALO_PAT_TOKEN", self._data.get("halo_pat_token", ""))
        self._data["vault_path"] = os.getenv("OBSIDIAN_VAULT_PATH", self._data.get("vault_path", ""))

    def save(self):
        """保存配置文件"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def validate(self):
        """验证必填字段"""
        errors = []
        if not self.get("halo_base_url"):
            errors.append("Halo 博客地址 (halo_base_url) 未配置")
        if not self.get("halo_pat_token"):
            errors.append("Halo Personal Access Token (halo_pat_token) 未配置")
        if not self.get("vault_path"):
            errors.append("Obsidian Vault 路径 (vault_path) 未配置")
        if errors:
            raise ValueError("\n".join(errors))
        return True

    def __repr__(self):
        return f"<Config path={self._path}>"
