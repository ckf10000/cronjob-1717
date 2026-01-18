# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     fetch_flight_actvity_order.py
# Description:  从劲旅平台抓取国内活动订单
# Author:       ASUS
# CreateDate:   2025/12/02
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from logging import Logger
import jobs.config as config
from aiohttp import CookieJar
from typing import Dict, Any, Optional
from qlv_helper.controller.order_detail import get_order_info_with_http
from qlv_helper.controller.order_table import get_domestic_activity_order_table
from jobs.redis_utils import redis_client_0, activity_order_queue, order_state_queue, gen_qlv_login_state_key, \
    gen_qlv_flight_order_key_prefix

"""
抓取逻辑
1. 获取劲旅平台登录状态数据，即cookie
2. 拼装参数，调用二方包的api，获取劲旅平台订单
3. 订单详情数据，放入redis，并将订单号放入redis活动订单队列
"""


async def executor_fetch_flight_activity_order_task(
        *, logger: Logger, qlv_domain: str, qlv_protocol: str, qlv_user_id: str, timeout: float = 60.0, retry: int = 0,
        semaphore: int = 10
) -> Optional[str]:
    playwright_state = await redis_client_0.get(key=gen_qlv_login_state_key(user_id=qlv_user_id))
    if not playwright_state:
        raise RuntimeError("Redis中劲旅登录状态数据已过期")
    # -------------------------
    # 获取订单列表（非并发）
    # -------------------------
    table_response = await get_domestic_activity_order_table(
        domain=qlv_domain, protocol=qlv_protocol, retry=retry, timeout=int(timeout), enable_log=True,
        cookie_jar=CookieJar(), playwright_state=playwright_state
    )
    pagination_data = table_response.get("data") or dict()
    domestic_activity_orders = pagination_data.get("data")
    # 如果没有订单
    if domestic_activity_orders:
        # -------------------------
        # ========== 并发执行 ==========
        # -------------------------
        # 限制最大并发数，防止接口被封
        sh = asyncio.Semaphore(semaphore)

        async def fetch_detail(order_id: int) -> Dict[str, Any]:
            """单个订单的详情请求（带并发锁）"""
            if order_id:
                async with sh:
                    try:
                        return await get_order_info_with_http(
                            order_id=order_id, timeout=int(timeout), domain=qlv_domain, protocol=qlv_protocol,
                            enable_log=True, retry=retry, cookie_jar=CookieJar(), playwright_state=playwright_state
                        )
                    except Exception as ex:
                        logger.error(f"获取订单：{order_id}详情失败：{ex}")
                        return dict(code=-1, message=str(ex), data=None)

        is_not_fetch: Dict[int, Any] = dict()
        domestic_activity_orders_dict: Dict[int, Any] = dict()
        for domestic_activity_order in domestic_activity_orders:
            order_id = domestic_activity_order.get("id")
            if order_id:
                key = gen_qlv_flight_order_key_prefix(
                    dep_city=domestic_activity_order.get("code_dep"), arr_city=domestic_activity_order.get("code_arr"),
                    dep_date=domestic_activity_order.get("dat_dep"), extend=order_id,
                    cabin=domestic_activity_order.get("cabin"), flight_no=domestic_activity_order.get("flight_no"),
                )
                if await activity_order_queue.exists(task=key) is False:
                    is_not_fetch[order_id] = key
                domestic_activity_orders_dict[order_id] = domestic_activity_order

        # 创建任务
        tasks = [asyncio.create_task(fetch_detail(order_id=order_id)) for order_id in is_not_fetch.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        flag = False
        for result in results:
            if isinstance(result, dict) and result.get("code") == 200 and "订单出票查看" in result.get("message"):
                order_data = result.get("data")
                order_id = order_data.get("id")
                key = is_not_fetch.get(order_id)
                activity_order = domestic_activity_orders_dict.get(order_id)
                remaining_time = activity_order.get("remaining_time")
                cache_data = await redis_client_0.get(key)
                if cache_data:
                    continue
                else:
                    if flag is False:
                        flag = True
                    activity_order.update(order_data)
                    await redis_client_0.set(key=key, value=activity_order, ex=remaining_time)
                    await activity_order_queue.lpush_if_not_exists(task=key)  # 原本是 LPUSH 到 activity 队列
                    await order_state_queue.lpush_if_not_exists(task=key)  # 原本是 LPUSH 到 order 队列
        if flag is True:
            msg: str = "任务执行成功"
            logger.info(msg)
            return msg
    logger.warning("任务执行结束，本次任务没有执行任何有效数据")


async def fetch_flight_activity_order_local_executor(
        *, logger: Logger, qlv_protocol: Optional[str] = None, qlv_domain: Optional[str] = None, sleep: int = 60,
        qlv_user_id: Optional[str] = None, timeout: Optional[float] = None, semaphore: Optional[int] = None,
        retry: Optional[int] = None
) -> None:
    while True:
        logger.info(f"开始抓取国内活动订单......")
        try:
            await executor_fetch_flight_activity_order_task(
                logger=logger, qlv_domain=qlv_domain or config.qlv_domain,
                qlv_protocol=qlv_protocol or config.qlv_protocol, timeout=timeout or config.timeout,
                retry=retry or config.retry, semaphore=semaphore or config.semaphore,
                qlv_user_id=qlv_user_id or config.qlv_user_id
            )
        except (RuntimeError, EnvironmentError, Exception) as e:
            logger.error(e)
        logger.info(f"抓取国内活动订单结束，等待<{sleep}>秒后将重试")
        await asyncio.sleep(sleep)


def register(executor):
    @executor.register(name="fetch_flight_activity_order")
    async def fetch_flight_activity_order():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[fetch_flight_activity_order] running with executor params: %s" % executor_params)
        return await executor_fetch_flight_activity_order_task(
            logger=g.logger, qlv_domain=executor_params.get("qlv_domain") or config.qlv_domain,
            qlv_protocol=executor_params.get("qlv_protocol") or config.qlv_protocol,
            semaphore=executor_params.get("semaphore") or config.semaphore,
            retry=executor_params.get("retry") or config.retry,
            timeout=executor_params.get("timeout") or config.timeout,
            qlv_user_id=executor_params.get("qlv_user_id") or config.qlv_user_id
        )


if __name__ == '__main__':
    from logging import INFO
    from log_utils import setup_logger, get_log_dir

    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="fetch_flight_activity_order", log_level=INFO
    )
    try:
        asyncio.run(fetch_flight_activity_order_local_executor(logger=logger))
    except (KeyboardInterrupt, SystemExit, Exception):
        logger.warning("程序已经退出")
