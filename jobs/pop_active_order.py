# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     pop_active_order.py
# Description:  弹出活动订单
# Author:       ASUS
# CreateDate:   2025/12/25
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from logging import Logger
import jobs.config as config
from typing import Any, Optional
from playwright_helper.utils.type_utils import RunResult
from jobs.common import get_browser_pool, get_playwright_executor
from jobs.redis_utils import redis_client_0, gen_qlv_login_state_key
from qlv_helper.controller.order_table import pop_will_expire_domestic_activity_order
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError


async def executor_pop_actvite_order_task(
        *, logger: Logger, qlv_protocol: str, qlv_domain: str, qlv_user_id: str, last_minute_threshold: int,
        timeout: float = 20.0, retry: int = 0, **kwargs: Any
) -> Optional[str]:
    playwright_state = await redis_client_0.get(key=gen_qlv_login_state_key(user_id=qlv_user_id))
    if not playwright_state:
        raise RuntimeError("Redis中劲旅登录状态数据已过期")
    pool = get_browser_pool(logger=logger)

    executor = get_playwright_executor(logger=logger, retry=retry, pool=pool)
    await executor.start()

    result: RunResult = await executor.run(
        callback=pop_will_expire_domestic_activity_order, storage_state=playwright_state, qlv_protocol=qlv_protocol,
        qlv_domain=qlv_domain, timeout=timeout, last_minute_threshold=last_minute_threshold
    )
    # 进程退出时关闭
    await pool.stop()
    await executor.stop()

    if result.success is True:
        data_list, is_pop = result.result
        if is_pop is True:
            msg: str = "任务执行成功"
            logger.info(msg)
            return msg
        else:
            logger.warning("任务执行结束，本次任务没有执行任何有效数据")
    else:
        raise result.error


async def pop_actvite_order_local_executor(
        *, logger: Logger, qlv_protocol: Optional[str] = None, qlv_domain: Optional[str] = None, sleep: int = 60,
        qlv_user_id: Optional[str] = None, last_minute_threshold: Optional[int] = None, timeout: Optional[float] = None,
        retry: Optional[int] = None, **kwargs: Any
) -> None:
    while True:
        logger.info(f"开始检验国内活动订单列表最晚出票时限的订单......")
        try:
            await executor_pop_actvite_order_task(
                logger=logger, qlv_protocol=qlv_protocol or config.qlv_protocol, timeout=timeout or config.timeout,
                retry=retry or config.retry, qlv_domain=qlv_domain or config.qlv_domain,
                last_minute_threshold=last_minute_threshold or config.last_minute_threshold,
                qlv_user_id=qlv_user_id or config.qlv_user_id
            )
        except (PlaywrightError, PlaywrightTimeoutError, RuntimeError, EnvironmentError, Exception) as e:
            logger.error(e)
        logger.info(f"检验国内活动订单列表最晚出票时限流程结束，等待<{sleep}>秒后将重试")
        await asyncio.sleep(sleep)


def register(executor):
    @executor.register(name="pop_actvite_order")
    async def pop_actvite_order():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[pop_actvite_order] running with executor params: %s" % executor_params)
        return await executor_pop_actvite_order_task(
            logger=g.logger, qlv_domain=executor_params.get("qlv_domain") or config.qlv_domain,
            qlv_protocol=executor_params.get("qlv_protocol") or config.qlv_protocol,
            last_minute_threshold=executor_params.get("last_minute_threshold") or config.last_minute_threshold,
            timeout=executor_params.get("timeout") or config.timeout,
            qlv_user_id=executor_params.get("qlv_user_id") or config.qlv_user_id,
            retry=executor_params.get("retry") or config.retry,
        )


if __name__ == '__main__':
    from logging import INFO
    from log_tuils import setup_logger, get_log_dir

    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="pop_actvite_order", log_level=INFO
    )
    try:
        asyncio.run(pop_actvite_order_local_executor(logger=logger, last_minute_threshold=30))
    except (KeyboardInterrupt, SystemExit, Exception):
        logger.warning("程序已经退出")
