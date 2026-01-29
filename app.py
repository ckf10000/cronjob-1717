# -*- coding: utf-8 -*-
import os
import sys
import json
import aiofiles
import importlib
import threading
from pyxxl import error
from aiohttp import web
from time import sleep, time
from datetime import datetime
from pyxxl.logger import LogBase
from pyxxl.schema import RunData
from threading import Lock, Timer
from urllib.parse import parse_qs
from pyxxl.types import LogRequest
from pyxxl.executor import Executor
from pyxxl.logger.disk import DiskLog
from typing import Optional, TypedDict
from watchdog.observers import Observer
from log_utils import logger, get_log_file
from pyxxl.server import routes, app_logger
from pyxxl import ExecutorConfig, PyxxlRunner
from watchdog.events import FileSystemEventHandler

_original_run_job = Executor.run_job

jobs_path = "jobs"

# 移除原来的 /log
routes._items = [
    r for r in routes._items
    if not (r.method == "POST" and r.path == "/log")
]


# 重新注册一个符合 XXL-Job Java Admin 解析规则的 /log
@routes.post("/log")
async def log(request: web.Request) -> web.Response:
    """
        {
        "logDateTim":0,     // 本次调度日志时间
        "logId":0,          // 本次调度日志ID
        "fromLineNum":0     // 日志开始行号，滚动加载日志
    }
    """
    data = await request.json()
    app_logger(request).debug("get log request %s" % data)
    task_log: LogBase = request.app["pyxxl_state"].task_log

    return web.json_response({
        "code": 200,
        "msg": "日志获取成功",  # 🚨 关键：不能是 None，必须是 ""
        "data": await task_log.get_logs(data),
    })


@routes.get("/healthCheck")
async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"code": 200, "msg": "当前系统状态良好", "data": None})


class LogResponse(TypedDict):
    fromLineNum: int
    toLineNum: int
    logContent: str
    isEnd: bool


async def hacked_get_logs(self, request: LogRequest, *, key: Optional[str] = None) -> LogResponse:
    # todo: 优化获取中间行的逻辑，缓存之前每行日志的大小然后直接seek
    key = key or self.key(request["logId"])
    logs = ""
    from_line = request["fromLineNum"]
    to_line_num = from_line - 1  # 👈 初始化为上一行
    is_end = False

    try:
        async with aiofiles.open(key, mode="r") as f:
            # 读取从第 1 行到 (from_line + tail - 1) 行
            for i in range(1, from_line + self.log_tail_lines):
                line = await f.readline()
                if line == "":
                    is_end = True
                    break
                if i >= from_line:
                    to_line_num = i
                    logs += line
    except FileNotFoundError as e:
        self.executor_logger.warning(str(e), exc_info=True)
        logs = "No such logid logs."
        is_end = True  # 文件不存在，也算“结束”
    return LogResponse(
        fromLineNum=request["fromLineNum"],
        toLineNum=to_line_num,
        logContent=logs,
        isEnd=is_end,
    )


DiskLog.get_logs = hacked_get_logs


def _get_mode(data: RunData):
    """
    从 executorParams 中解析 mode
    支持:
      mode=discard
      mode=serial
      {"mode":"discard"}   # 如果你用的是 JSON
    """
    params = data.executorParams or ""

    # JSON 风格
    if params.startswith("{") and params.endswith("}"):
        try:
            return json.loads(params).get("mode")
        except (Exception,):
            return None

    # querystring 风格
    qs = parse_qs(params)
    return qs.get("mode", [None])[0]


async def hacked_run_job(self, data: RunData):
    handler_obj = self.handler.get(data.executorHandler)
    if not handler_obj:
        self.executor_logger.warning("handler %s not found." % data.executorHandler)
        raise error.JobNotFoundError("handler %s not found." % data.executorHandler)

    mode = _get_mode(data)
    force_discard = (mode == "discard")

    async with self.lock:
        current_task = self.tasks.get(data.jobId)
        queue = self.get_queue(data.jobId)

        # 没有在跑 → 直接执行
        if not current_task and queue.empty():
            self.tasks[data.jobId] = self._create_task(data)
            return "Running"

        self.executor_logger.warning(
            "jobId=%s handler=%s mode=%s running, strategy=%s",
            data.jobId,
            data.executorHandler,
            mode,
            data.executorBlockStrategy,
        )

        # 💣 Executor 级丢弃（Admin 以为是 SERIAL）
        if force_discard:
            self.executor_logger.warning(
                f"[DISCARD_BY_PARAM] jobId={data.jobId} "
                f"handler={data.executorHandler} "
                f"logId={data.logId} params={data.executorParams}"
            )

            # 💡 关键：创建空日志文件
            log_file_path = os.path.join(
                self.config.log_local_dir,
                f"pyxxl-{data.logId}.log"
            )
            # 确保目录存在
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

            # 生成日志内容
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_content = (
                f"[{timestamp}] INFO - Task discarded by executor.\n"
                f"[{timestamp}] INFO - Reason: Execution mode is 'discard'.\n"
                f"[{timestamp}] INFO - Job ID: {data.jobId}, Log ID: {data.logId}\n"
                f"[{timestamp}] INFO - Handler: {data.executorHandler}\n"
                f"[{timestamp}] INFO - Parameters: {data.executorParams}\n"
            )

            # 创建空文件（异步）
            async with aiofiles.open(log_file_path, "w") as f:
                await f.write(log_content)

            start_time = int(time() * 1000)
            # 返回 200 给 admin
            await self.xxl_client.callback(
                data.logId,
                start_time,
                code=200,  # 200 = Admin 显示“执行成功”
                # msg=msg,  # 👈 这个会显示在「执行备注」
                msg=""  # 执行备注将什么都不显示。不要传 None，一定要是 ""（空字符串），否则 XXL-Job Java 端可能会写成 "null"。
            )

            return "DISCARDED"

        # 否则：走 XXL 原始 SERIAL / COVER / DISCARD 逻辑
        return await _original_run_job(self, data)


# 🔥 打补丁
Executor.run_job = hacked_run_job

# ---------------------------------------------------
# 1. 配置 Pyxxl 执行器（官方规范）
# ---------------------------------------------------
config = ExecutorConfig(
    xxl_admin_baseurl=os.getenv("XXL_JOB_ADMIN_ADDRESS", "http://192.168.3.240:18070/xxl-job-admin/api/"),
    executor_app_name=os.getenv("XXL_JOB_EXECUTOR_APPNAME", "playwright-cronjob-executor-1717"),

    # 官方推荐字段名称
    executor_listen_host="0.0.0.0",
    executor_listen_port=int(os.getenv("XXL_JOB_EXECUTOR_PORT", 9996)),

    # 这里指定 Admin 可访问的地址（必须是真实 IP + 端口 或域名）
    executor_url=os.getenv("XXL_JOB_EXECUTOR_URL", "http://192.168.3.240:9996/"),
    # 执行器绑定的http服务的url,xxl-admin通过这个host来回调pyxxl执行器.
    # Default: "http://{executor_listen_host}:{executor_listen_port}"

    access_token=os.getenv("XXL_JOB_ACCESS_TOKEN", "Abc123456"),
    executor_log_path=get_log_file(file_name="pyxxl.log"),

    # 建议开启 debug，便于定位注册成功与否
    debug=True,
)

executor = PyxxlRunner(config)


# ---------------------------------------------------
# 2. 通用加载任务函数
# ---------------------------------------------------
def load_job_module(module_path):
    """通用加载任务模块并注册的函数"""
    try:
        module_name = module_path.split('.')[-1]

        # 查看 JobHandler 类的属性
        job_handler = executor.handler
        # 步骤1：取消注册旧任务
        if hasattr(job_handler, '_handlers'):
            handlers_dict = job_handler._handlers

            if isinstance(handlers_dict, dict):
                logger.info(f"[pyxxl] 当前注册的任务数量: {len(handlers_dict)}")

                if module_name in handlers_dict:
                    # 保存旧处理器信息（用于调试）
                    old_handler = handlers_dict[module_name]
                    logger.info(f"[pyxxl] 旧处理器信息: {type(old_handler)}")

                    # 取消注册
                    del handlers_dict[module_name]
                    logger.info(f"[pyxxl] ✓ 已取消注册任务: {module_name}")

                    # 验证取消注册
                    if module_name not in handlers_dict:
                        logger.info(f"[pyxxl] ✓ 取消注册验证成功")
                    else:
                        logger.error(f"[pyxxl] ✗ 取消注册验证失败")
                else:
                    logger.info(f"[pyxxl] 任务 {module_name} 未注册，直接进行新注册")
            else:
                logger.warning(f"[pyxxl] _handlers 不是字典: {type(handlers_dict)}")
        else:
            logger.warning(f"[pyxxl] 无法找到任务字典，跳过取消注册步骤")

        # 步骤2：卸载模块
        if module_path in sys.modules:
            # 在卸载前尝试清理模块状态
            old_module = sys.modules[module_path]

            # 清理可能的模块级状态
            if hasattr(old_module, '__pyxxl_cleanup__'):
                try:
                    old_module.__pyxxl_cleanup__()
                    logger.info(f"[pyxxl] 执行模块清理函数")
                except Exception as e:
                    logger.warning(f"[pyxxl] 模块清理失败: {e}")

            del sys.modules[module_path]
            logger.info(f"[pyxxl] ✓ 已卸载模块: {module_path}")

        # 步骤3：清除导入缓存
        importlib.invalidate_caches()
        logger.info(f"已清除导入缓存")

        # 步骤4：重新导入模块
        logger.info(f"重新导入模块: {module_path}")
        module = importlib.import_module(module_path)

        # 步骤5：重新注册任务
        if hasattr(module, "register"):
            # 检查注册函数是否可调用
            if callable(module.register):
                module.register(executor)
                logger.info(f"[pyxxl] ✓ 成功调用 register 函数")

                # 步骤6：验证注册结果
                if hasattr(job_handler, '_handlers') and isinstance(job_handler._handlers, dict):
                    if module_name in job_handler._handlers:
                        new_handler = job_handler._handlers[module_name]
                        logger.info(f"[pyxxl] ✓ 任务注册成功，新处理器: {type(new_handler)}")
                    else:
                        logger.error(f"[pyxxl] ✗ 任务注册失败，任务未出现在处理器字典中")
                else:
                    logger.warning(f"[pyxxl] 无法验证注册结果")
            else:
                logger.error(f"register 属性不可调用: {type(module.register)}")
        else:
            logger.warning(f"{module_path} 未定义 register(executor)，跳过")

    except Exception as e:
        logger.error(f"任务<{module_path}>注册失败，原因: {e}")


def inspect_pyxxl_structure():
    """查看 PyXXL 执行器的实际结构"""
    logger.info("=== PyXXL 执行器结构分析 ===")

    # 查看执行器类的属性
    import pyxxl
    executor_class = pyxxl.executor.Executor
    class_attrs = [attr for attr in dir(executor_class) if not attr.startswith('__')]
    logger.info(f"Executor类属性: {class_attrs}")

    # 查看实例属性
    instance_attrs = [attr for attr in dir(executor) if not attr.startswith('_')]
    logger.info(f"执行器实例属性: {instance_attrs}")

    # 特别查看字典类型的属性
    for attr in dir(executor):
        try:
            value = getattr(executor, attr)
            if isinstance(value, dict):
                logger.info(f"字典属性 '{attr}': 包含 {len(value)} 个键")
                if value:
                    logger.info(f"  前几个键: {list(value.keys())[:3]}")
        except (Exception,):
            pass


# ---------------------------------------------------
# 3. 自动扫描 jobs/ 目录并调用 register(executor)
# ---------------------------------------------------
def auto_load_jobs():
    if not os.path.exists(jobs_path):
        logger.warning("jobs 目录不存在，跳过加载")
        return

    # 先清空现有的处理器（避免重复注册错误）
    job_handler = executor.handler
    if hasattr(job_handler, '_handlers') and isinstance(job_handler._handlers, dict):
        job_handler._handlers.clear()
        logger.info(f"已清空所有任务处理器")

    for filename in os.listdir(jobs_path):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = f"{jobs_path}.{module_name}"

            try:
                # 直接导入并注册，不先检查是否已存在
                module = importlib.import_module(module_path)

                if hasattr(module, "register"):
                    module.register(executor)
                    logger.info(f"加载任务: {module_path}")
                else:
                    logger.warning(f"{module_path} 未定义 register(executor)，跳过")

            except Exception as e:
                logger.error(f"加载任务 {module_path} 失败: {e}")


# ---------------------------------------------------
# 4. 使用 watchdog 动态监控目录变化并重新加载任务
# ---------------------------------------------------
class DebouncedJobFileEventHandler(FileSystemEventHandler):
    def __init__(self, delay=2.0):  # 2秒防抖
        self.delay = delay
        self._timer = None
        self._lock = Lock()
        self._pending_events = set()
        logger.info(f"[watchdog] 防抖事件处理器已初始化，防抖时间: {delay}秒")

    def on_any_event(self, event):
        """监控所有事件，用于调试"""
        if not event.is_directory:
            logger.info(f"[watchdog] 捕获事件: {event.event_type} - {event.src_path}")

    def _process_events(self):
        logger.info(f"[watchdog] 开始处理积压的事件")
        with self._lock:
            events = self._pending_events.copy()
            self._pending_events.clear()
            self._timer = None

        logger.info(f"[watchdog] 需要处理 {len(events)} 个事件")
        for event_path in events:
            self._handle_single_event(event_path)

    @staticmethod
    def _handle_single_event(event_path):
        logger.info(f"[watchdog] 处理单个事件: {event_path}")
        if event_path.endswith(".py") and not event_path.endswith("__init__.py"):
            if os.path.exists(event_path):
                logger.info(f"[watchdog] 重新加载模块: {event_path}")
                module_name = os.path.basename(event_path)[:-3]
                module_path = f"{jobs_path}.{module_name}"

                # 卸载模块
                if module_path in sys.modules:
                    del sys.modules[module_path]
                    logger.info(f"[watchdog] 已卸载模块: {module_path}")

                # 重新加载
                try:
                    load_job_module(module_path)
                except Exception as e:
                    logger.warning(f"[watchdog] 重新加载失败: {e}")
            else:
                logger.error(f"[watchdog] 文件不存在，跳过: {event_path}")

    def _schedule_processing(self, event_path):
        logger.info(f"[watchdog] 调度处理: {event_path}")
        with self._lock:
            self._pending_events.add(event_path)

            if self._timer is not None:
                self._timer.cancel()
                logger.info(f"[watchdog] 取消之前的定时器")

            self._timer = Timer(self.delay, self._process_events)
            self._timer.start()
            logger.info(f"[watchdog] 新定时器已启动，将在 {self.delay} 秒后处理")

    def on_modified(self, event):
        logger.info(f"[watchdog] 文件修改事件: {event.src_path}")
        if not event.is_directory and event.src_path.endswith(".py") and not event.src_path.endswith("__init__.py"):
            logger.info(f"[watchdog] 检测到Python文件修改: {event.src_path}")
            self._schedule_processing(event.src_path)

    def on_created(self, event):
        logger.info(f"[watchdog] 文件创建事件: {event.src_path}")
        if not event.is_directory and event.src_path.endswith(".py") and not event.src_path.endswith("__init__.py"):
            logger.info(f"[watchdog] 检测到新Python文件: {event.src_path}")
            self._schedule_processing(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            logger.info(f"[watchdog] 文件已删除: {event.src_path}")
            module_name = os.path.basename(event.src_path)[:-3]
            module_path = f"jobs.{module_name}"

            if module_path in sys.modules:
                del sys.modules[module_path]
                logger.info(f"[watchdog] 模块 {module_name} 已卸载")


def start_job_watchdog():
    logger.info(f"[watchdog] 初始化文件监控...")

    # 检查监控目录是否存在
    if not os.path.exists(jobs_path):
        logger.warning(f"[watchdog] 警告: 监控目录 {jobs_path} 不存在!")
        return

    logger.info(f"[watchdog] 监控目录: {os.path.abspath(jobs_path)}")

    event_handler = DebouncedJobFileEventHandler(delay=3.0)  # 3秒防抖
    observer = Observer()

    try:
        observer.schedule(event_handler, jobs_path, recursive=False)
        observer.start()
        logger.info(f"[watchdog] 开始监控 {jobs_path} 目录变化...")

        # 持续运行监控
        while observer.is_alive():
            sleep(1)

    except Exception as e:
        logger.error(f"[watchdog] 监控异常: {e}")
    finally:
        logger.error("[watchdog] 停止文件监控...")
        observer.stop()
        observer.join()


def watchdog_health_check():
    while True:
        if not watchdog_thread.is_alive():
            logger.error("Watchdog 线程已终止！")
        sleep(10)


# ---------------------------------------------------
# 5. 启动 Pyxxl 执行器并启动监控
# ---------------------------------------------------
if __name__ == "__main__":
    # for logger_name in logging.root.manager.loggerDict:
    #     logger = logging.getLogger(logger_name)
    #     for handler in logger.handlers:
    #         handler.setFormatter(xxl_log_common.TASK_FORMATTER)
    #
    # 首先加载一次任务
    logger.info("扫描并加载 jobs 目录中的任务...")
    auto_load_jobs()

    # 启动 watchdog 监控文件变化的线程
    # start_job_watchdog()
    # 启动 watchdog（非守护线程）
    watchdog_thread = threading.Thread(
        target=start_job_watchdog,
        name="watchdog-monitor",
        daemon=False  # 必须设为非守护线程！
    )
    watchdog_thread.start()
    logger.info("文件监控线程已启动")

    # 启动执行器
    logger.info("启动 XXL-JOB Python 执行器...")
    try:
        executor.run_executor()

        # 在主线程启动后
        health_check_thread = threading.Thread(
            target=watchdog_health_check,
            daemon=True
        )
        health_check_thread.start()
    except KeyboardInterrupt:
        logger.error("接收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"执行器异常: {e}")
    finally:
        logger.error("执行器已关闭")
