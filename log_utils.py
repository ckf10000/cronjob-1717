# -*- coding: utf-8 -*-
import os as _os
import sys as _sys
import logging as _logging
from pyxxl.ctx import g as _g
from pathlib import Path as _Path
import pyxxl.setting as _xxl_setting
from datetime import datetime as _datetime
from loguru import logger as _loguru_logger
import pyxxl.logger.common as _xxl_log_common
from pyxxl.logger.disk import DiskLog as _DiskLog
from pyxxl.log import executor_logger as _executor_logger
from logging.handlers import RotatingFileHandler as _RotatingFileHandler
from playwright_helper.utils.file_handle import get_caller_dir as _get_caller_dir


def get_root_dir() -> str:
    return _get_caller_dir()


def get_log_dir() -> str:
    root_dir = get_root_dir()
    log_dir = _os.path.join(root_dir, 'logs')
    _Path(log_dir).mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file(file_name: str) -> str:
    log_dir = get_log_dir()
    log_file = _os.path.join(log_dir, file_name)
    _Path(log_file).touch(exist_ok=True)
    return log_file


def get_screenshot_dir() -> str:
    root_dir = get_root_dir()
    log_dir = _os.path.join(root_dir, 'screenshots')
    if not _os.path.exists(log_dir):
        _os.makedirs(log_dir)
    return log_dir


def set_pathname(record: _logging.LogRecord):
    pathname = getattr(record, "pathname", None)
    if pathname.find("site-packages") != - 1:
        record.pathname = pathname.split("site-packages")[-1]
    elif pathname.find("Lib") != - 1:
        record.pathname = pathname.split("Lib")[-1]
    elif pathname.find("jobs") != - 1:
        record.pathname = _os.sep + _os.path.join("jobs", _os.path.basename(record.pathname))
    else:
        record.pathname = _os.sep + _os.path.basename(record.pathname)


class SafeFormatter(_logging.Formatter):
    def format(self, record):
        log_id = getattr(record, "logId", None)
        job_id = getattr(record, "jobId", None)
        if log_id:
            record.logId = f"- [logId={record.logId}] "
        else:
            record.logId = ""
        if job_id:
            record.jobId = f"- [jobId={record.jobId}] "
        else:
            record.jobId = ""
        source = "TASK" if log_id or job_id else "EXECUTOR"
        # set_pathname(record=record)
        record.source = f"- [{source}] "
        return super().format(record)


CUSTOM_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level:<8}</level> | "
    "<yellow>{extra[source]}</yellow> | "
    "<magenta>{extra[jobId]}</magenta>"
    "<blue>{extra[logId]}</blue>"
    "<level>{message}</level>"
    "<green>{extra[logger_name]}</green><cyan>{extra[pathname]}</cyan>:<cyan>({extra[funcName]}</cyan>:<cyan>{extra[lineno]})</cyan>"
)

CUSTOM_CONSOLE_FORMAT_NOT_DISPLAY = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level:<8}</level> | "
    "<yellow>{extra[source]}</yellow> | "
    "<magenta>{extra[jobId]}</magenta>"
    "<blue>{extra[logId]}</blue>"
    "<level>{message}</level>"
)

CUSTOM_FILE_FORMAT_STR = (
    "%(asctime)s.%(msecs)03d - [PID-%(process)d] - [%(threadName)s-%(thread)d] - [%(levelname)s] "
    "%(source)s%(jobId)s%(logId)s- %(message)s - %(pathname)s:(%(funcName)s:%(lineno)d)"
)

UNIFIED_FORMATTER = SafeFormatter(
    CUSTOM_FILE_FORMAT_STR,
    datefmt=_xxl_log_common.TASKDATE_FORMAT,
)

DEFAULT_FILE_SIZE = 50 * 1024 * 1024
DEFAULT_BACKUP_FILE_COUNT = 5


class FileHandler(_logging.FileHandler):
    def emit(self, record: _logging.LogRecord) -> None:
        xxl_kwargs = _g.try_get_run_data()
        record.logId = xxl_kwargs.logId if xxl_kwargs else None
        record.jobId = xxl_kwargs.jobId if xxl_kwargs else None
        return super().emit(record)


class LoguruHandler(_logging.Handler):
    def emit(self, record: _logging.LogRecord):
        try:
            level = _loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # ----------------------------
        # 1️⃣ 提取上下文
        # ----------------------------
        # jobId / logId 动态显示
        xxl_kwargs = _g.try_get_run_data()
        job_id = xxl_kwargs.jobId if xxl_kwargs else ""
        log_id = xxl_kwargs.logId if xxl_kwargs else ""
        source = "TASK" if job_id or log_id else "EXECUTOR"

        # ----------------------------
        # 2️⃣ 绑定 context（核心）
        # ----------------------------
        # set_pathname(record=record)
        extra = {
            "source": source,
            "jobId": f"jobId={job_id} | " if job_id else "",
            "logId": f"logId={log_id} | " if log_id else "",
            "logger_name": f" | {record.name} | " if source == "EXECUTOR" else "",
            "pathname": record.pathname,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        frame, depth = _logging.currentframe(), 2
        while frame and frame.f_code.co_filename == _logging.__file__:
            frame = frame.f_back
            depth += 1

        _loguru_logger.bind(**extra).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())

        # xxl_kwargs = _g.try_get_run_data()
        # record.logId = xxl_kwargs.logId if xxl_kwargs else "NotInTask"
        # return super().emit(record)


def hacked_setup_logging(path: str, name: str, level: int = _logging.INFO) -> _logging.Logger:
    logger = _logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # -------------------------
    # 1️⃣ Console → Loguru
    # -------------------------
    console_handler = LoguruHandler()
    logger.addHandler(console_handler)

    _loguru_logger.remove()  # 移除默认 handler
    _loguru_logger.add(
        _sys.stdout,
        level=level,
        colorize=True,
        backtrace=False,
        diagnose=False,
        format=CUSTOM_CONSOLE_FORMAT_NOT_DISPLAY,  # 🔥 就是这一行
    )

    # ② file → logging（给系统 / 运维 / admin）
    file_handler = _RotatingFileHandler(
        path, maxBytes=DEFAULT_FILE_SIZE, backupCount=DEFAULT_BACKUP_FILE_COUNT, delay=True, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(UNIFIED_FORMATTER)
    logger.addHandler(file_handler)

    # =========================
    # 5️⃣ 三方库日志
    # =========================
    for name in ["urllib3", "requests", "charset_normalizer", "playwright", "asyncio", "aiohttp.access"]:
        log = _logging.getLogger(name)
        log.setLevel(level)  # 降低这些库的日志级别
        if not any(isinstance(h, LoguruHandler) for h in log.handlers):
            log.addHandler(console_handler)

        if file_handler and not any(isinstance(h, _RotatingFileHandler) for h in log.handlers):
            log.addHandler(file_handler)
        log.propagate = False
    # access_logger = _logging.getLogger("aiohttp.access")
    # access_logger.setLevel(level)
    # access_logger.propagate = False  # 防止再传给 root
    # 只加一次 handler（防重复）
    # if not any(isinstance(h, LoguruHandler) for h in access_logger.handlers):
    #     access_logger.addHandler(console_handler)
    return logger


def hacked_get_disk_logger(self, log_id: int, *, stdout: bool = True, level: int = _logging.INFO) -> _logging.Logger:
    logger = _logging.getLogger("pyxxl.task_log.disk.task-{%s}" % log_id)
    logger.propagate = False
    logger.setLevel(level)

    if stdout:
        console_handler = LoguruHandler()
        logger.addHandler(console_handler)

        _loguru_logger.remove()  # 移除默认 handler
        _loguru_logger.add(
            _sys.stdout,
            level=level,
            colorize=True,
            backtrace=False,
            diagnose=False,
            format=CUSTOM_CONSOLE_FORMAT_NOT_DISPLAY,  # 🔥 就是这一行
        )

    file_handler = FileHandler(self.key(log_id), delay=True, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(UNIFIED_FORMATTER)
    logger.addHandler(file_handler)
    return logger


# 🔥 正式接管 pyxxl
_xxl_setting.setup_logging = hacked_setup_logging
_DiskLog.get_logger = hacked_get_disk_logger


def setup_logger(
        *, logs_dir: str, file_name: str, log_level: int = _logging.DEBUG, display_path: bool = False
) -> _logging.Logger:
    logger = _logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(log_level)
    logger.propagate = False

    # -------------------------
    # 1️⃣ Console → Loguru
    # -------------------------
    console_handler = LoguruHandler()
    logger.addHandler(console_handler)

    _loguru_logger.remove()  # 移除默认 handler
    _loguru_logger.add(
        _sys.stdout,
        level=log_level,
        colorize=True,
        backtrace=False,
        diagnose=False,
        format=CUSTOM_CONSOLE_FORMAT if display_path is True else CUSTOM_CONSOLE_FORMAT_NOT_DISPLAY,  # 🔥 就是这一行
    )

    # === 日志文件名称 ===
    LOG_FILE = _os.path.join(logs_dir, f"{file_name}_{_datetime.now().strftime('%Y%m%d')}.log")

    # ② file → logging（给系统 / 运维 / admin）
    file_handler = _RotatingFileHandler(
        LOG_FILE, maxBytes=DEFAULT_FILE_SIZE, backupCount=DEFAULT_BACKUP_FILE_COUNT, delay=True, encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(UNIFIED_FORMATTER)
    logger.addHandler(file_handler)

    # =========================
    # 5️⃣ 三方库日志
    # =========================
    for name in ["urllib3", "requests", "charset_normalizer", "playwright", "asyncio", "aiohttp.access"]:
        log = _logging.getLogger(name)
        log.setLevel(log_level)  # 降低这些库的日志级别
        if not any(isinstance(h, LoguruHandler) for h in log.handlers):
            log.addHandler(console_handler)

        if file_handler and not any(isinstance(h, _RotatingFileHandler) for h in log.handlers):
            log.addHandler(file_handler)
        log.propagate = False

    return logger


logger = _executor_logger
if __name__ == '__main__':
    print(get_log_dir())
