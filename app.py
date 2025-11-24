# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     app.py
# Description:  执行器的入口
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import os
import importlib
from pyxxl import ExecutorConfig, PyxxlRunner

# ---------------------------------------------------
# 1. 配置 Pyxxl 执行器（保持你的写法 + 官方规范）
# ---------------------------------------------------
config = ExecutorConfig(
    xxl_admin_baseurl=os.getenv("XXL_JOB_ADMIN_ADDRESS"),
    executor_app_name=os.getenv("XXL_JOB_EXECUTOR_APPNAME", "python-executor"),

    # 官方推荐字段名称
    executor_listen_host="0.0.0.0",
    executor_listen_port=int(os.getenv("XXL_JOB_EXECUTOR_PORT", 9999)),

    # 这里指定 Admin 可访问的地址（必须是真实 IP + 端口 或域名）
    executor_url=os.getenv("XXL_JOB_EXECUTOR_URL"),
    # 执行器绑定的http服务的url,xxl-admin通过这个host来回调pyxxl执行器.
    # Default: "http://{executor_listen_host}:{executor_listen_port}"

    access_token=os.getenv("XXL_JOB_ACCESS_TOKEN", ""),

    # 建议开启 debug，便于定位注册成功与否
    debug=True,
)

executor = PyxxlRunner(config)


# ---------------------------------------------------
# 2. 自动扫描 jobs/ 目录并调用 register(executor)
# ---------------------------------------------------
def auto_load_jobs():
    jobs_path = "jobs"

    if not os.path.exists(jobs_path):
        print("[pyxxl] jobs 目录不存在，跳过加载")
        return

    for filename in os.listdir(jobs_path):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = f"{jobs_path}.{module_name}"

            try:
                module = importlib.import_module(module_path)

                if hasattr(module, "register"):
                    module.register(executor)
                    print(f"[pyxxl] Loaded job: {module_name}")
                else:
                    print(f"[pyxxl] {module_name} 未定义 register(executor)，跳过")

            except Exception as e:
                print(f"[pyxxl] 加载任务 {module_name} 失败: {e}")


# 扫描并加载任务
auto_load_jobs()

# ---------------------------------------------------
# 3. 启动 Pyxxl 执行器
# ---------------------------------------------------
if __name__ == "__main__":
    print("[pyxxl] 启动 XXL-JOB Python 执行器...")
    executor.run_executor()
