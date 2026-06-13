"""
同步日志 - 记录每次同步操作的结果
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_LOG_PATH = Path.home() / ".config" / "halo-obsidian-sync" / "sync_log.json"


class SyncLog:
    """管理同步日志"""

    def __init__(self, path: str = None):
        self._path = Path(path) if path else DEFAULT_LOG_PATH
        self._entries = []
        self.load()

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except Exception:
                self._entries = []
        else:
            self._entries = []

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)

    def add(self, entry: Dict[str, Any]):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._entries.append(entry)
        # 只保留最近 500 条
        if len(self._entries) > 500:
            self._entries = self._entries[-500:]
        self.save()

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._entries[-limit:][::-1]

    def get_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e.get("file_path") == file_path][::-1]

    def get_stats(self) -> Dict[str, int]:
        stats = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "error": 0, "conflict": 0}
        for e in self._entries:
            stats["total"] += 1
            status = e.get("status", "unknown")
            if status in stats:
                stats[status] += 1
        return stats
