# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     fetch_flight_actvity_order_by_qlv.py
# Description:  从劲旅平台抓取国内活动订单
# Author:       ASUS
# CreateDate:   2025/12/02
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from typing import Dict, Any
from aiohttp import CookieJar
from logging import Logger, getLogger
from qlv_helper.controller.order_detail import get_order_info_with_http
from qlv_helper.controller.order_table import get_domestic_activity_order_table
from jobs.redis_helper import redis_client, activity_order_queue, order_state_queue

"""
抓取逻辑
1. 获取劲旅平台登录状态数据，即cookie
2. 拼装参数，调用二方包的api，获取劲旅平台订单
3. 订单详情数据，放入redis，并将订单号放入redis活动订单队列
"""


async def get_flight_activity_order_by_qlv(logger: Logger, domain: str, protocol: str, semaphore: int = 10):
    playwright_state = await redis_client.get(key=redis_client.gen_qlv_login_state_key())
    if not playwright_state:
        raise RuntimeError("Redis中劲旅登录状态数据已过期")
    timeout: int = 5
    retry: int = 1

    # -------------------------
    # 获取订单列表（非并发）
    # -------------------------
    table_response = await get_domestic_activity_order_table(
        domain=domain, protocol=protocol, retry=retry, timeout=timeout, enable_log=True,
        cookie_jar=CookieJar(), playwright_state=playwright_state
    )
    pagination_data = table_response.get("data") or dict()
    domestic_activity_orders = pagination_data.get("data")
    # 如果没有订单
    if not domestic_activity_orders:
        return list()

    # -------------------------
    # ========== 并发执行 ==========
    # -------------------------
    # 限制最大并发数，防止接口被封
    sh = asyncio.Semaphore(semaphore)

    async def fetch_detail(order_id: int) -> Dict[str, Any]:
        """单个订单的详情请求（带并发锁）"""
        async with sh:
            try:
                return await get_order_info_with_http(
                    order_id=order_id, timeout=timeout, domain=domain,
                    protocol=protocol, enable_log=True, retry=retry,
                    cookie_jar=CookieJar(), playwright_state=playwright_state
                )
            except Exception as ex:
                logger.error(f"获取订单：{order_id}详情失败：{ex}")
                return dict(code=-1, message=str(ex), data=None)

    domestic_activity_orders_dict = {x.get("id"): x for x in domestic_activity_orders}

    # 创建任务
    tasks = [asyncio.create_task(fetch_detail(order_id=order_id)) for order_id, _ in
             domestic_activity_orders_dict.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    msg = list()
    for result in results:
        if isinstance(result, dict) and result.get("code") == 200 and "订单出票查看" in result.get("message"):
            order_data = result.get("data")
            order_id = order_data.get("id")
            activity_order = domestic_activity_orders_dict.get(order_id)
            remaining_time = activity_order.get("remaining_time")
            key = redis_client.gen_qlv_flight_order_key_prefix(
                dep_city=activity_order.get("code_dep"), arr_city=activity_order.get("code_arr"),
                dep_date=activity_order.get("dat_dep")[:10], extend=order_id
            )
            cache_data = await redis_client.get(key)
            if cache_data:
                continue
            else:
                activity_order.update(order_data)
                await redis_client.set(key=key, value=activity_order, ex=remaining_time)
                await activity_order_queue.lpush_if_not_exists(task=key)  # 原本是 LPUSH 到 activity 队列
                await order_state_queue.lpush_if_not_exists(task=key)  # 原本是 LPUSH 到 order 队列
        else:
            msg.append(str(result))
    if msg:
        return RuntimeError("<br>".join(msg))
    else:
        return "任务执行成功"


def register(executor):
    @executor.register(name="fetch_flight_activity_order_to_redis_by_qlv")
    async def fetch_flight_activity_order_to_redis_by_qlv():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[fetch_flight_activity_order_to_redis_by_qlv] running with executor params: %s" % executor_params)
        return await get_flight_activity_order_by_qlv(
            logger=g.logger, domain=executor_params.get("domain"), protocol=executor_params.get("protocol"),
            semaphore=executor_params.get("semaphore")
        )


if __name__ == '__main__':
    logger = getLogger(__name__)
    asyncio.run(get_flight_activity_order_by_qlv(logger=logger, domain="pekzhongqihl.qlv88.com", protocol="https"))
