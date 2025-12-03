# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     update_qlv_order_state.py
# Description:  更新劲旅平台订单状态
# Author:       ASUS
# CreateDate:   2025/11/28
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from aiohttp import CookieJar
from typing import List, Dict, Any
from jobs.redis_helper import redis_client, order_state_queue
from qlv_helper.controller.order_detail import get_order_info_with_http

"""
更新逻辑：
1. 从processing队列恢复上次崩溃滞留下的任务
2. redis队列弹出key，key为空，任务跳过
2. redis中的劲旅平台登录状态数据已过期，key扔回队列，抛异常
3. redis中的订单详情数据已过期，key丢弃，任务跳过
4. 调用劲旅平台API失败，key扔回队列，抛异常
5. 调用劲旅平台API成功，获取状态数据失败，可能是解析异常，key扔回队列，抛异常
6. 如果任务参数中，discard_state参数存在值，需要根据此参数判断redis中的数据是否被丢弃
7. 如果订单状态显示为其他状态，则更新redis中的订单状态，key扔回队列
"""


async def update_order_state(
        domain: str = "pekzhongqihl.qlv88.com", protocol: str = "https", discard_state: List[str] = None
) -> str:
    """
    更新订单状态
    :param domain: 劲旅平台域名
    :param protocol: http or https
    :param discard_state: 基于该参数，判断是否要将订单状态数据丢弃，若丢弃，则将key的过期时间设置为1
    :return:
    """
    # 1. 恢复processing队列中的任务
    await order_state_queue.recover()
    # 2. 从队尾取出（FIFO）
    key = await order_state_queue.pop()
    if not key:
        return "Redis队列中没有需要更新状态的订单数据，任务跳过"

    playwright_state = await redis_client.get(key=redis_client.gen_qlv_login_state_key())
    if not playwright_state:
        await order_state_queue.requeue(task=key)
        raise RuntimeError("Redis中劲旅登录状态数据已过期")
    timeout: int = 5
    retry: int = 1
    order_id = key.split(":")[-1]
    order_info = await redis_client.get(key=key)
    if not order_info:
        await order_state_queue.finish(task=key)
        return f"劲旅订单：{order_id}，在Redis中的详情数据已经过期，任务跳过"
    response: Dict[str, Any] = await get_order_info_with_http(
        order_id=order_id, timeout=timeout, domain=domain, protocol=protocol, enable_log=True, retry=retry,
        cookie_jar=CookieJar(), playwright_state=playwright_state
    )
    """"
    消息结构：
    {'code': 200, 'message': '订单出票查看', 'data': {'receipted_ota': 645.9, 'kickback': 0, 'id': 155715, 'raw_order_no': '4624992464-4624992464', 'trip_type': '单程', 'stat_order': '待处理', 'stat_opration': '收款完成', 'flights': [{'ticket_state': '未出票', 'p_name': '李晓璐', 'p_type': '成人', 'id_type': '身份证', 'id_no': '420103198310012461', 'birth_day': '1983-10-01', 'age': 42, 'gender': '女', 'new_nation': 'CN|中国', 'card_issue_place': 'CN|中国', 'id_valid_dat': '1900-01-01', 'price_std': 600, 'price_sell': 575.9, 'tax_air': 50, 'tax_fuel': 20, 'pnr': 'XE小(000000) 大(000000)【 RT 】【 PAT 】【 RTC 】', 'code_dep': 'SYX', 'code_arr': 'TYN', 'ticket_no': ''}], 'peoples': [{'ticket_state': '未出票', 'p_name': '李晓璐', 'p_type': '成人', 'id_type': '身份证', 'id_no': '420103198310012461', 'birth_day': '1983-10-01', 'age': 42, 'gender': '女', 'new_nation': 'CN|中国', 'card_issue_place': 'CN|中国', 'id_valid_dat': '1900-01-01', 'price_std': 600, 'price_sell': 575.9, 'tax_air': 50, 'tax_fuel': 20, 'pnr': 'XE小(000000) 大(000000)【 RT 】【 PAT 】【 RTC 】', 'code_dep': 'SYX', 'code_arr': 'TYN', 'ticket_no': ''}]}}
    """
    if response.get("code") != 200 or response.get("message") != "订单出票查看":
        await order_state_queue.requeue(task=key)
        raise RuntimeError(str(response))
    data = response.get("data")
    stat_order = data.get("stat_order")
    stat_opration = data.get("stat_opration")
    if not stat_order or not stat_opration:
        await order_state_queue.requeue(task=key)
        raise RuntimeError(f"劲旅订单：{order_id}，详情页面数据解析异常")
    if discard_state:
        if stat_order in discard_state:
            await redis_client.expire(key=key, expire=1)
            # 3. 数据可以丢弃
            await order_state_queue.finish(task=key)
            return f"劲旅订单：{order_id}，当前的订单状态：{stat_order}，在Redis中的详情数据将被丢弃"
    order_info["stat_order"] = stat_order
    order_info["stat_opration"] = stat_opration
    ttl = await redis_client.ttl(key=key)
    if ttl < 1:
        last_time_ticket = order_info.get("last_time_ticket")
        ttl = redis_client.general_key_vid(last_time_ticket=last_time_ticket)
    await redis_client.set(key=key, value=order_info, ex=ttl)
    # 4. key还需要继续使用，重新扔回队列
    await order_state_queue.requeue(task=key)
    return f"任务执行成功，劲旅订单：{order_id}，在Redis中的订单状态已更新"


def register(executor):
    @executor.register(name="update_qlv_order_state")
    async def update_qlv_order_state():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[update_qlv_order_state] running with executor params: %s" % executor_params)
        return await update_order_state(
            domain=executor_params.get("domain", "pekzhongqihl.qlv88.com"),
            protocol=executor_params.get("protocol", "https"),
            discard_state=executor_params.get("discard_state", ["出票完成", "出票成功", "已作废"])
        )


if __name__ == '__main__':
    asyncio.run(update_order_state(discard_state=[
        "出票完成",
        "出票成功",
        "已作废"
    ]))
