import os
import sys
import logging
import importlib
import threading
from time import sleep
from threading import Lock, Timer
from watchdog.observers import Observer
from pyxxl import ExecutorConfig, PyxxlRunner
from watchdog.events import FileSystemEventHandler
from log_tuils import setup_logger, get_log_dir, get_log_file

jobs_path = "jobs"

logger = logging.getLogger("root")

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
    executor_log_path=get_log_file("executor.log"),

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
        logger.info(f"[pyxxl] 已清除导入缓存")

        # 步骤4：重新导入模块
        logger.info(f"[pyxxl] 重新导入模块: {module_path}")
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
                logger.error(f"[pyxxl] register 属性不可调用: {type(module.register)}")
        else:
            logger.warning(f"[pyxxl] {module_path} 未定义 register(executor)，跳过")

    except Exception as e:
        logger.error(f"[pyxxl] 任务<{module_path}>注册失败，原因: {e}")


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
        logger.warning("[pyxxl] jobs 目录不存在，跳过加载")
        return

    # 先清空现有的处理器（避免重复注册错误）
    job_handler = executor.handler
    if hasattr(job_handler, '_handlers') and isinstance(job_handler._handlers, dict):
        job_handler._handlers.clear()
        logger.info(f"[pyxxl] 已清空所有任务处理器")

    for filename in os.listdir(jobs_path):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = f"{jobs_path}.{module_name}"

            try:
                # 直接导入并注册，不先检查是否已存在
                module = importlib.import_module(module_path)

                if hasattr(module, "register"):
                    module.register(executor)
                    logger.info(f"[pyxxl] 加载任务: {module_path}")
                else:
                    logger.warning(f"[pyxxl] {module_path} 未定义 register(executor)，跳过")

            except Exception as e:
                logger.error(f"[pyxxl] 加载任务 {module_path} 失败: {e}")


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
    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="app", log_level=logging.DEBUG
    )
    # 首先加载一次任务
    logger.info("[pyxxl] 扫描并加载 jobs 目录中的任务...")
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
    logger.info("[pyxxl] 启动 XXL-JOB Python 执行器...")
    try:
        executor.run_executor()

        # 在主线程启动后
        health_check_thread = threading.Thread(
            target=watchdog_health_check,
            daemon=True
        )
        health_check_thread.start()
    except KeyboardInterrupt:
        logger.error("\n[pyxxl] 接收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"[pyxxl] 执行器异常: {e}")
    finally:
        logger.error("[pyxxl] 执行器已关闭")

