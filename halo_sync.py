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
    python halo_sync.py pull <post_name>
    python halo_sync.py pull-all
    python halo_sync.py log
    python halo_sync.py stats
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
from src.sync_log import SyncLog


def _validate_config():
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(f"[错误] 配置不完整: {e}")
        print("请先运行: python halo_sync.py init")
        sys.exit(1)
    return config


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
    config = _validate_config()

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
    config = _validate_config()
    engine = SyncEngine(config)
    results = engine.sync_all(force=args.force)

    print(f"\n批量同步完成，共处理 {len(results)} 篇笔记:\n")
    for r in results:
        icon = {"created": "✓", "updated": "↑", "skipped": "-", "error": "✗", "conflict": "⚠"}.get(r["status"], "?")
        print(f"  [{icon}] {r['status']:8s} | {r['message']}")

    errors = [r for r in results if r["status"] == "error"]
    conflicts = [r for r in results if r["status"] == "conflict"]
    if errors:
        print(f"\n同步失败: {len(errors)} 篇")
    if conflicts:
        print(f"\n冲突待解决: {len(conflicts)} 篇 (使用 --force 强制覆盖)")
    if errors:
        sys.exit(1)


def cmd_watch(args):
    """实时监听 Vault 变更并自动同步"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[错误] 未安装 watchdog，请运行: pip install watchdog")
        sys.exit(1)

    config = _validate_config()
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


# ==================== 双向同步命令 ====================

def cmd_pull(args):
    """从 Halo 拉取单篇文章到 Obsidian"""
    config = _validate_config()
    engine = SyncEngine(config)

    result = engine.pull_post(args.post_name, target_dir=args.dir)
    print(f"\n拉取结果:")
    print(f"  状态: {result['status']}")
    print(f"  文件: {result.get('file_path')}")
    print(f"  消息: {result['message']}")

    if result["status"] == "error":
        sys.exit(1)


def cmd_pull_all(args):
    """从 Halo 拉取所有文章到 Obsidian"""
    config = _validate_config()
    engine = SyncEngine(config)

    print("正在获取 Halo 文章列表...")
    results = engine.pull_all_posts(target_dir=args.dir)

    print(f"\n拉取完成，共处理 {len(results)} 篇:\n")
    success = 0
    for r in results:
        icon = "✓" if r["status"] == "pulled" else "✗"
        print(f"  [{icon}] {r['status']:8s} | {r['message']}")
        if r["status"] == "pulled":
            success += 1

    print(f"\n成功拉取: {success} / {len(results)}")


# ==================== 日志与统计 ====================

def cmd_log(args):
    """查看同步日志"""
    log = SyncLog()
    entries = log.list(limit=args.limit)

    if not entries:
        print("暂无同步记录")
        return

    print(f"\n最近 {len(entries)} 次同步记录:\n")
    print(f"  {'时间':20s} {'状态':8s} {'文件':30s} {'消息'}")
    print(f"  {'-'*80}")
    for e in entries:
        ts = e.get("timestamp", "")[:19]
        status = e.get("status", "")
        file_path = e.get("file_path", "")
        file_short = os.path.basename(file_path) if file_path else "-"
        message = e.get("message", "")
        print(f"  {ts:20s} {status:8s} {file_short:30s} {message}")


def cmd_stats(args):
    """查看同步统计"""
    log = SyncLog()
    stats = log.get_stats()

    print("\n=== 同步统计 ===\n")
    print(f"  总同步次数: {stats['total']}")
    print(f"  新增:        {stats['created']}")
    print(f"  更新:        {stats['updated']}")
    print(f"  跳过:        {stats['skipped']}")
    print(f"  失败:        {stats['error']}")
    print(f"  冲突:        {stats['conflict']}")

    if stats['total'] > 0:
        success_rate = (stats['created'] + stats['updated'] + stats['skipped']) / stats['total'] * 100
        print(f"\n  成功率: {success_rate:.1f}%")


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

    # pull
    p_pull = subparsers.add_parser("pull", help="从 Halo 拉取单篇文章")
    p_pull.add_argument("post_name", help="Halo 文章的 metadata.name (唯一标识)")
    p_pull.add_argument("-d", "--dir", help="保存目录（缺省使用 Vault 根目录）")
    p_pull.set_defaults(func=cmd_pull)

    # pull-all
    p_pull_all = subparsers.add_parser("pull-all", help="从 Halo 拉取所有文章")
    p_pull_all.add_argument("-d", "--dir", help="保存目录（缺省使用 Vault 根目录）")
    p_pull_all.set_defaults(func=cmd_pull_all)

    # log
    p_log = subparsers.add_parser("log", help="查看同步日志")
    p_log.add_argument("-n", "--limit", type=int, default=30, help="显示最近 N 条记录 (默认 30)")
    p_log.set_defaults(func=cmd_log)

    # stats
    p_stats = subparsers.add_parser("stats", help="查看同步统计")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
