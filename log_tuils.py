# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  ceair-web-ticket-checkout-executor
# FileName:     log_tuils.py
# Description:  日志工具模块
# Author:       ASUS
# CreateDate:   2025/12/16
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from playwright_helper.utils.file_handle import get_caller_dir


def get_root_dir() -> str:
    return get_caller_dir()


def get_log_dir() -> str:
    root_dir = get_root_dir()
    log_dir = os.path.join(root_dir, 'logs')
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file(file_name: str) -> str:
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, file_name)
    Path(log_file).touch(exist_ok=True)
    return log_file


def get_screenshot_dir() -> str:
    root_dir = get_root_dir()
    log_dir = os.path.join(root_dir, 'screenshots')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return log_dir


def setup_logger(logs_dir: str, file_name: str, log_level: int = logging.DEBUG) -> logging.Logger:
    try:
        from loguru import logger

        class InterceptHandler(logging.Handler):
            def emit(self, record):
                try:
                    level = logger.level(record.levelname).name
                except ValueError:
                    level = record.levelno

                frame, depth = logging.currentframe(), 2
                while frame and frame.f_code.co_filename == logging.__file__:
                    frame = frame.f_back
                    depth += 1

                logger.opt(
                    depth=depth,
                    exception=record.exc_info
                ).log(level, record.getMessage())

        # === 日志文件名称 ===
        LOG_FILE = os.path.join(logs_dir, f"{file_name}_{datetime.now().strftime('%Y%m%d')}.log")

        # === 移除默认 logger（防止重复输出）===
        logger.remove()

        # === 控制台输出（带颜色）===

        # logger.add(
        #     sink=lambda msg: print(msg, end=""),
        #     colorize=True,
        #     format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        #            "<level>{level: <8}</level> | "
        #            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        #            "<level>{message}</level>",
        #     level=log_level
        # )
        logger.add(
            sys.stdout,
            colorize=True,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
        )

        # === 文件输出（按大小轮转、异步安全）===
        logger.add(
            LOG_FILE,
            rotation="10 MB",  # 每个日志文件最大 10MB
            retention="7 days",  # 保留 7 天日志
            encoding="utf-8",
            enqueue=True,  # 异步写入（支持 Playwright 异步爬虫）
            backtrace=True,  # 打印错误堆栈
            diagnose=True,  # 打印详细错误上下文
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
        )

        # 4. ⭐⭐ logging → loguru（核心）
        logging.root.handlers = [InterceptHandler()]
        logging.root.setLevel(log_level)

        # 5. 控制第三方库日志级别
        for name in ["asyncio", "urllib3", "requests", "charset_normalizer", "playwright", "root"]:
            logging.getLogger(name).setLevel(log_level)

        return logger
    except (ImportError, Exception):
        # 清除所有配置
        logging.root.handlers.clear()

        LOG_FORMAT: str = '%(asctime)s - [PID-%(process)d] - [Thread-%(thread)d] - [%(levelname)s] - %(message)s'
        # LOG_FORMAT: str = '%(asctime)s - [PID-%(process)d] - [Thread-%(thread)d] - [%(levelname)s] - %(message)s - <%(funcName)s> - [Line-%(lineno)d] - %(filename)s'
        # DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

        # 创建 handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))

        # 配置 root logger
        logging.root.setLevel(logging.DEBUG)
        logging.root.addHandler(handler)

        # 但需要为特定 logger 降低级别
        for name in ["asyncio", "urllib3", "requests", "charset_normalizer", "playwright", "root"]:
            log = logging.getLogger(name)
            log.setLevel(logging.DEBUG)  # 降低这些库的日志级别
            log.propagate = True  # 让他们传播到 root

        # 获取 playwright logger
        logger = logging.getLogger("playwright")
        logger.setLevel(logging.DEBUG)
        logger.propagate = True  # 传播到 root，使用 root 的格式
        return logger


if __name__ == '__main__':
    print(get_log_dir())
