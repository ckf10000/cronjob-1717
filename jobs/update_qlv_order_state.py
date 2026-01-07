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
from logging import Logger
from aiohttp import CookieJar
import jobs.config as config
from typing import List, Dict, Any, Optional
from qlv_helper.controller.order_detail import get_order_info_with_http
from jobs.redis_utils import redis_client_0, order_state_queue, gen_qlv_login_state_key, qlv_flight_order_key_convert_dict

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


async def executor_update_order_state_task(
        *, logger: Logger, qlv_domain: str, qlv_protocol: str, qlv_user_id: str, discard_state: List[str],
        enable_log: bool = True, timeout: float = 60.0, retry: int = 1
) -> Optional[str]:
    # 1. 恢复processing队列中的任务
    await order_state_queue.recover()
    # 2. 从队尾取出（FIFO）
    key = await order_state_queue.pop()
    if not key:
        logger.warning("Redis队列中没有需要更新状态的订单数据，任务跳过")
        return

    playwright_state = await redis_client_0.get(key=gen_qlv_login_state_key(user_id=qlv_user_id))
    if not playwright_state:
        await order_state_queue.requeue(task=key)
        raise RuntimeError("Redis中劲旅登录状态数据已过期")
    order_info = qlv_flight_order_key_convert_dict(key=key)
    order_id = order_info.get("extend")
    order_info = await redis_client_0.get(key=key)
    if not order_info:
        await order_state_queue.finish(task=key)
        logger.warning(f"劲旅订单：{order_id}，在Redis中的详情数据已经过期，任务跳过")
        return
    response: Dict[str, Any] = await get_order_info_with_http(
        order_id=order_id, timeout=int(timeout), domain=qlv_domain, protocol=qlv_protocol, enable_log=enable_log,
        retry=retry, cookie_jar=CookieJar(), playwright_state=playwright_state
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
            await redis_client_0.expire(key=key, expire=1)
            # 3. 数据可以丢弃
            await order_state_queue.finish(task=key)
            logger.warning(f"劲旅订单：{order_id}，当前的订单状态：{stat_order}，在Redis中的详情数据将被丢弃")
            return
    order_info["stat_order"] = stat_order
    order_info["stat_opration"] = stat_opration
    ttl = await redis_client_0.ttl(key=key)
    if ttl < 1:
        last_time_ticket = order_info.get("last_time_ticket")
        ttl = redis_client_0.general_key_vid(last_time_ticket=last_time_ticket)
    await redis_client_0.set(key=key, value=order_info, ex=ttl)
    # 4. key还需要继续使用，重新扔回队列
    await order_state_queue.requeue(task=key)
    msg: str = f"任务执行成功，劲旅订单：{order_id}，在Redis中的订单状态已更新"
    logger.info(msg)
    return msg


async def update_order_state_local_executor(
        *, logger: Logger, qlv_protocol: Optional[str] = None, qlv_domain: Optional[str] = None, sleep: int = 60,
        qlv_user_id: Optional[str] = None, timeout: Optional[float] = None, discard_state: Optional[List[str]] = None,
        retry: Optional[int] = None
) -> None:
    while True:
        logger.info(f"开始更新缓存中的劲旅订单状态......")
        try:
            await executor_update_order_state_task(
                logger=logger, qlv_domain=qlv_domain or config.qlv_domain,
                qlv_protocol=qlv_protocol or config.qlv_protocol, timeout=timeout or config.timeout,
                retry=retry or config.retry, qlv_user_id=qlv_user_id or config.qlv_user_id,
                discard_state=discard_state or config.discard_state,
            )
        except (RuntimeError, EnvironmentError, Exception) as e:
            logger.error(e)
        logger.info(f"更新缓存中的劲旅订单状态结束，等待<{sleep}>秒后将重试")
        await asyncio.sleep(sleep)


def register(executor):
    @executor.register(name="update_qlv_order_state")
    async def update_qlv_order_state():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[update_qlv_order_state] running with executor params: %s" % executor_params)
        return await executor_update_order_state_task(
            logger=g.logger, qlv_domain=executor_params.get("qlv_domain") or config.qlv_domain,
            qlv_protocol=executor_params.get("qlv_protocol") or config.qlv_protocol,
            qlv_user_id=executor_params.get("qlv_user_id") or config.qlv_user_id,
            timeout=executor_params.get("timeout") or config.timeout,
            retry=executor_params.get("retry") or config.retry,
            discard_state=executor_params.get("discard_state") or config.discard_state
        )


if __name__ == '__main__':
    from logging import INFO
    from log_tuils import setup_logger, get_log_dir

    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="update_qlv_order_state", log_level=INFO
    )
    try:
        asyncio.run(update_order_state_local_executor(logger=logger))
    except (KeyboardInterrupt, SystemExit, Exception):
        logger.warning("程序已经退出")
