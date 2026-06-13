#!/usr/bin/env python3
"""
Halo Obsidian Sync - CLI 入口
实现 Obsidian Markdown 笔记一键同步到 Halo 博客

安装:
    pip install -r requirements.txt

使用:
    python halo_sync.py init
    python halo_sync.py sync "/path/to/note.md"
    python halo_sync.py sync-all
    python halo_sync.py watch
"""
import sys
import os
import json
import argparse
from pathlib import Path

# 确保能从源目录加载
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir / "src"))

from src.config import Config
from src.sync_engine import SyncEngine


def cmd_init(args):
    """初始化配置"""
    config = Config()
    print("=== Halo Obsidian Sync 配置向导 ===\n")

    base_url = input("Halo 博客地址 (如 https://blog.example.com): ").strip()
    token = input("Halo Personal Access Token: ").strip()
    vault = input("Obsidian Vault 路径 (回车使用默认 ~/Documents/Obsidian Vault): ").strip()
    if not vault:
        vault = str(Path.home() / "Documents" / "Obsidian Vault")

    config.set("halo_base_url", base_url)
    config.set("halo_pat_token", token)
    config.set("vault_path", vault)
    config.save()
    print(f"\n配置已保存到: {config._path}")


def cmd_sync(args):
    """同步单篇笔记"""
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(f"[错误] 配置不完整: {e}")
        print("请先运行: python halo_sync.py init")
        sys.exit(1)

    file_path = args.file
    if not os.path.isabs(file_path):
        file_path = os.path.join(config.get("vault_path"), file_path)
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        print(f"[错误] 文件不存在: {file_path}")
        sys.exit(1)

    engine = SyncEngine(config)
    result = engine.sync_note(file_path, force=args.force)
    print(f"\n同步结果:")
    print(f"  状态: {result['status']}")
    print(f"  文章标识: {result.get('post_name')}")
    print(f"  消息: {result['message']}")

    if result["status"] == "error":
        sys.exit(1)


def cmd_sync_all(args):
    """批量同步所有标记了 halo_sync: true 的笔记"""
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(f"[错误] 配置不完整: {e}")
        print("请先运行: python halo_sync.py init")
        sys.exit(1)

    engine = SyncEngine(config)
    results = engine.sync_all(force=args.force)

    print(f"\n批量同步完成，共处理 {len(results)} 篇笔记:\n")
    for r in results:
        icon = {"created": "✓", "updated": "↑", "skipped": "-", "error": "✗"}.get(r["status"], "?")
        print(f"  [{icon}] {r['status']:8s} | {r['message']}")

    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print(f"\n同步失败: {len(errors)} 篇")
        sys.exit(1)


def cmd_watch(args):
    """实时监听 Vault 变更并自动同步"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[错误] 未安装 watchdog，请运行: pip install watchdog")
        sys.exit(1)

    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(f"[错误] 配置不完整: {e}")
        sys.exit(1)

    engine = SyncEngine(config)
    vault_path = config.get("vault_path")

    class SyncHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory or not event.src_path.endswith(".md"):
                return
            if ".obsidian" in event.src_path:
                return
            print(f"\n[检测变更] {event.src_path}")
            result = engine.sync_note(event.src_path)
            print(f"  → {result['status']}: {result['message']}")

    observer = Observer()
    observer.schedule(SyncHandler(), vault_path, recursive=True)
    observer.start()
    print(f"\n=== 监听模式已启动 ===")
    print(f"监听路径: {vault_path}")
    print(f"自动同步标记了 halo_sync: true 的 Markdown 文件")
    print(f"按 Ctrl+C 停止\n")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("\n监听已停止")


def main():
    parser = argparse.ArgumentParser(
        description="Halo Obsidian Sync - 将 Obsidian 笔记同步到 Halo 博客",
        prog="halo_sync.py",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # init
    p_init = subparsers.add_parser("init", help="初始化配置")
    p_init.set_defaults(func=cmd_init)

    # sync
    p_sync = subparsers.add_parser("sync", help="同步单篇笔记")
    p_sync.add_argument("file", help="Markdown 文件路径（相对于 Vault 或绝对路径）")
    p_sync.add_argument("-f", "--force", action="store_true", help="强制重新同步")
    p_sync.set_defaults(func=cmd_sync)

    # sync-all
    p_all = subparsers.add_parser("sync-all", help="批量同步所有笔记")
    p_all.add_argument("-f", "--force", action="store_true", help="强制重新同步")
    p_all.set_defaults(func=cmd_sync_all)

    # watch
    p_watch = subparsers.add_parser("watch", help="实时监听并自动同步")
    p_watch.set_defaults(func=cmd_watch)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
