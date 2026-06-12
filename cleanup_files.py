"""
定期文件清理脚本
按时间保留最新的指定数量文件
"""
import os
import time
import logging
import yaml
import schedule
import glob
from typing import List, Dict
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict:
    """加载配置文件"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cleanup_folder(folder_config: Dict):
    """
    清理单个文件夹

    Args:
        folder_config: 文件夹配置字典，包含 path, keep_count, file_pattern
    """
    folder_path = folder_config["path"]
    keep_count = folder_config.get("keep_count", 50)
    file_pattern = folder_config.get("file_pattern", "*")

    if not os.path.exists(folder_path):
        logger.warning(f"文件夹不存在，跳过: {folder_path}")
        return

    # 获取匹配的文件列表
    search_pattern = os.path.join(folder_path, file_pattern)
    files = glob.glob(search_pattern)

    # 只保留文件，排除目录
    files = [f for f in files if os.path.isfile(f)]

    if len(files) <= keep_count:
        logger.debug(f"[{folder_path}] 文件数量 {len(files)} <= 保留数量 {keep_count}，无需清理")
        return

    # 按修改时间排序（最新的在前）
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    # 要删除的文件
    files_to_delete = files[keep_count:]

    logger.info(f"[{folder_path}] 总文件数: {len(files)}，保留最新 {keep_count} 个，删除 {len(files_to_delete)} 个")

    # 删除文件
    deleted_count = 0
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            logger.debug(f"已删除: {file_path}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"删除文件失败 {file_path}: {e}")

    logger.info(f"[{folder_path}] 清理完成，已删除 {deleted_count} 个文件")


def run_cleanup(config: Dict):
    """执行一次清理任务"""
    cleanup_config = config.get("cleanup", {})

    if not cleanup_config.get("enabled", True):
        logger.info("清理任务未启用")
        return

    folders = cleanup_config.get("folders", [])
    if not folders:
        logger.info("没有配置需要清理的文件夹")
        return

    logger.info("=" * 60)
    logger.info("开始执行文件清理任务")
    logger.info("=" * 60)

    for folder_config in folders:
        cleanup_folder(folder_config)

    logger.info("=" * 60)
    logger.info("文件清理任务完成")
    logger.info("=" * 60)


def run_scheduled():
    """运行定时任务"""
    config = load_config()
    cleanup_config = config.get("cleanup", {})
    interval = cleanup_config.get("interval_minutes", 60)

    schedule.every(interval).minutes.do(lambda: run_cleanup(config))

    logger.info(f"文件清理定时任务已启动，每 {interval} 分钟执行一次")
    logger.info("按 Ctrl+C 停止")

    # 立即执行一次
    run_cleanup(config)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("定时任务已停止")


def main():
    """主函数"""
    import sys

    config = load_config()

    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        if config["cleanup"].get("enabled", True):
            run_scheduled()
        else:
            logger.info("定时任务未启用，执行单次清理")
            run_cleanup(config)
    else:
        run_cleanup(config)


if __name__ == "__main__":
    main()
