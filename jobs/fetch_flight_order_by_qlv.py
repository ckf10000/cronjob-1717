# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     fetch_flight_order_by_qlv.py
# Description:  从劲旅平台抓取订单
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any
from jobs.redis_helper import redis_client
from http_helper.client.async_proxy import HttpClientFactory, HttpClientError

"""
从劲旅平台抓取订单，存放至Redis中，存放有效时长86400秒(1天)
"""
order_api_config = {
    "protocol": "http",
    "address": "192.168.3.240:18080"
}


async def lock_order(policy_name: str, operator: str, air_cos: str = None, order_pk: int = 0,
                     order_src_cat: str = None) -> Optional[Dict[str, Any]]:
    order_http_client = HttpClientFactory(
        protocol=order_api_config.get('protocol'),
        domain=order_api_config.get('address'),
        timeout=10,
        retry=2,
        enable_log=True
    )
    json_data = {
        "policy_name": policy_name,
        "air_cos": air_cos,
        "order_pk": order_pk,
        "order_src_cat": order_src_cat,
        "operator": operator
    }
    return await order_http_client.request(
        method="post",
        url="/api/v1/agent/order/lock",
        json_data=json_data,
        is_end=True
    )


async def unlock_order(order_id: int) -> Optional[Dict[str, Any]]:
    order_http_client = HttpClientFactory(
        protocol=order_api_config.get('protocol'),
        domain=order_api_config.get('address'),
        timeout=10,
        retry=2,
        enable_log=True
    )
    json_data = {
        "order_id": order_id,
        "operator": "周汗林",
        "remark": "机器人锁单获取订单信息，不下单",
        "order_state": "0",
        "order_lose_type": "政策",
    }
    return await order_http_client.request(
        method="post",
        url="/api/v1/agent/order/unlock",
        json_data=json_data,
        is_end=True
    )


def general_key_vid(last_time_ticket: str) -> int:
    last_time = datetime.strptime(last_time_ticket, '%Y-%m-%d %H:%M:%S')
    delta = last_time - datetime.now()
    seconds = delta.total_seconds()
    if seconds >= 0:
        return int(seconds)
    else:
        return 86400


async def fetch_flight_order(policy_name: str, operator: str, air_cos: str = None, order_pk: int = 0,
                             order_src_cat: str = None) -> str:
    resp_body = await lock_order(
        policy_name=policy_name, operator=operator, air_cos=air_cos, order_pk=order_pk, order_src_cat=order_src_cat
    )
    if resp_body.get("code") == 200 and resp_body.get("data") and isinstance(resp_body.get("data"), dict):
        data = resp_body.get("data")
        order_id = data.get("id")
        flights = data.get("flights")
        last_time_ticket = data.get("last_time_ticket")
        # 只取第一段航程的数据作为key的关键信息
        flight = flights[0] if isinstance(flights, list) and len(flights) > 0 else dict()
        dep_date = redis_client.iso_to_standard_datetimestr(datestr=flight.get("dat_dep"), time_zone_step=8)
        key_vid = general_key_vid(
            last_time_ticket=last_time_ticket if last_time_ticket and len(last_time_ticket) > 0 else dep_date
        )
        key = redis_client.gen_qlv_flight_order_key_prefix(
            dep_city=flight.get("code_dep"), arr_city=flight.get("code_arr"), dep_date=dep_date[:10],
            extend=order_id
        )
        await redis_client.set(key=key, value=data, ex=key_vid)
        await redis_client.lpush(key=redis_client.gen_qlv_flight_activity_order_list_key(), value=key)
        await redis_client.lpush(key=redis_client.gen_qlv_flight_order_state_list_key(), value=key)
        return "任务执行成功"
        # order_id = data.get("id")
        # unlock_resp_body = await unlock_order(order_id=order_id)
        # if unlock_resp_body.get("code") == 200:
        #     return "task executed successfully"
        # else:
        #     return unlock_resp_body
    elif "无单可锁" in resp_body.get("message"):
        return "任务执行完成, 劲旅平台无单可锁"
    else:
        raise HttpClientError(json.dumps(resp_body, ensure_ascii=False))


""""
发生异常时，executor认为是任务执行失败，正常执行结束，executor认为是任务执行成功
"""


def register(executor):
    @executor.register(name="fetch_flight_order_to_redis_by_qlv")
    async def fetch_flight_order_to_redis_by_qlv():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[fetch_flight_order_to_redis_by_qlv] running with executor params: %s" % executor_params)
        return await fetch_flight_order(**executor_params)


if __name__ == '__main__':
    import asyncio

    asyncio.run(fetch_flight_order(
        policy_name="TP>YJ-1", operator="周汗林", order_pk=158299
    ))
