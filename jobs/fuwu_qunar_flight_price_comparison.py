# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     fuwu_qunar_flight_price_comparison.py
# Description:  去哪儿服务平台航班比价
# Author:       ASUS
# CreateDate:   2025/11/26
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from logging import Logger
import jobs.config as config
from typing import Optional, Dict, Any
from jobs.common import fetch_tts_agent_tool_total, get_fuwu_qunar_price_comparison_template, \
    send_message_to_dingdin_robot
from jobs.redis_utils import redis_client_0, activity_order_queue, iso_to_standard_datestr, iso_to_standard_datetimestr

"""
比价逻辑
1. 从redis队列尾部中取出即将要比价的订单key，从K,V存储中取出订单详情
2. 详情有值，调用去哪儿平台API比价；无值则扔掉key，直接结束任务
3. 详情有值，订单key插入redis队列队首，无值则忽略此步骤
"""


async def executor_fuwu_qunar_flight_price_comparison_task(
        *, logger: Logger, qlv_domain: str, qlv_protocol: str, uuid: Optional[str], headers: Optional[Dict[str, Any]],
        timeout: int = 60, retry: int = 0, low_threshold: int = 0, high_threshold: int = 0, enable_log: bool = True
) -> Optional[str]:
    # 1. 恢复processing队列中的任务
    await activity_order_queue.recover()
    # 2. 从队尾取出（FIFO）
    key = await activity_order_queue.pop()
    if key:
        cache_data = await redis_client_0.get(key)
        if cache_data:
            order_id = cache_data.get("id")
            flights = cache_data.get("flights")
            peoples = cache_data.get("peoples")
            # 只取第一段航程的数据作为比价的检索数据
            flight = flights[0] if isinstance(flights, list) and len(flights) > 0 else dict()
            people = peoples[0] if isinstance(peoples, list) and len(peoples) > 0 else dict()
            if flight.get("flight_no"):
                flight_no = flight.get("flight_no")
            else:
                flight_no = cache_data.get("flight_no")
            price_std = people.get("price_std")
            price_sell = people.get("price_sell")
            city_dep = flight.get("city_dep").strip() if flight.get("city_dep") else ""
            city_arr = flight.get("city_arr").strip() if flight.get("city_arr") else ""
            code_dep = flight.get("code_dep").strip() if flight.get("code_dep") else ""
            code_arr = flight.get("code_arr").strip() if flight.get("code_arr") else ""
            dat_dep = iso_to_standard_datetimestr(
                datestr=flight.get("dat_dep").strip(), time_zone_step=8
            ) if flight.get("dat_dep") else cache_data.get("dat_dep")
            if flight.get("dat_dep"):
                dep_date = iso_to_standard_datestr(datestr=flight.get("dat_dep"), time_zone_step=8)
            else:
                dep_date = cache_data.get("dat_dep")[:10]
            if cache_data.get("cabin"):
                order_cabin = cache_data.get("cabin")
            else:
                order_cabin = flight.get("cabin")
            source_name = cache_data.get("source_name")
            response = await fetch_tts_agent_tool_total(
                flight_no=flight_no, dpt=code_dep, arr=code_arr, flight_date=dep_date, timeout=timeout, retry=retry,
                enable_log=enable_log, uuid=uuid, headers=headers
            )
            data = response.get("data") or dict()
            if response.get("ret") is True:
                if data and isinstance(data, dict) and response.get("data").get("orderList"):
                    order_list = data.get("orderList") or list()
                    if order_list:
                        logger.info(f"已检索到航班{flight_no}数据")
                        url = f"https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport={code_dep}&searchArrivalAirport={code_arr}&searchDepartureTime={dep_date}&searchArrivalTime={dep_date}&nextNDays=0&startSearch=true&fromCode={city_dep}&toCode={city_arr}&from=flight_dom_search&lowestPrice=null"
                        # 排序（默认升序）,reverse=False, sellPrice 外放底价， sellFloorPrice 外放追价底价
                        low_sell_price_list = [x for x in order_list if price_sell > x.get("sellPrice") > 0]
                        low_view_price_list = [x for x in order_list if price_sell > x.get("maxViewPrice") > 0]
                        high_sell_price_list = [x for x in order_list if x.get("sellPrice") > price_sell]
                        high_wiew_price_list = [x for x in order_list if x.get("maxViewPrice") > price_sell]
                        if low_sell_price_list or low_view_price_list:
                            if low_sell_price_list:
                                low_sell_price_list.sort(key=lambda x: x["sellPrice"])
                                min_price = low_sell_price_list[0]["sellPrice"]
                                ota_cabin = low_sell_price_list[0]["cabin"]
                            else:
                                low_view_price_list.sort(key=lambda x: x["maxViewPrice"])
                                min_price = low_view_price_list[0]["maxViewPrice"]
                                ota_cabin = low_view_price_list[0]["cabin"]
                            reduction_price = round(price_sell - min_price, 1)
                            if reduction_price > low_threshold:
                                extend_msg = f"{min_price}\n\n**降价**: {reduction_price}"
                                action_card_message = get_fuwu_qunar_price_comparison_template(
                                    order_id=order_id, flight_no=flight_no, price_std=price_std, qlv_domain=qlv_domain,
                                    price_sell=price_sell, min_price=extend_msg, qunar_url=url, order_cabin=order_cabin,
                                    ota_cabin=ota_cabin, source_ota=source_name, dat_dep=dat_dep,
                                    qlv_protocol=qlv_protocol
                                )
                                await send_message_to_dingdin_robot(
                                    message=action_card_message, message_type="actionCard"
                                )
                            else:
                                min_price = f"{min_price}，降价: {reduction_price}，小于或等于降价阈值: {low_threshold}，不报告警"
                        elif high_sell_price_list or high_wiew_price_list:
                            if high_sell_price_list:
                                high_sell_price_list.sort(key=lambda x: x["sellPrice"])
                                min_price = high_sell_price_list[0]["sellPrice"]
                                ota_cabin = high_sell_price_list[0]["cabin"]
                            else:
                                high_wiew_price_list.sort(key=lambda x: x["maxViewPrice"])
                                min_price = high_wiew_price_list[0]["maxViewPrice"]
                                ota_cabin = high_wiew_price_list[0]["cabin"]
                            increase_price = round(min_price - price_sell, 1)
                            # if increase_price > high_threshold:
                            if increase_price > high_threshold and ota_cabin != order_cabin:
                                extend_msg = f"{min_price}\n\n**涨价**: {increase_price}"
                                action_card_message = get_fuwu_qunar_price_comparison_template(
                                    order_id=order_id, flight_no=flight_no, price_std=price_std, qlv_domain=qlv_domain,
                                    price_sell=price_sell, min_price=extend_msg, qunar_url=url, order_cabin=order_cabin,
                                    ota_cabin=ota_cabin, source_ota=source_name, dat_dep=dat_dep,
                                    qlv_protocol=qlv_protocol
                                )
                                await send_message_to_dingdin_robot(
                                    message=action_card_message, message_type="actionCard"
                                )
                            else:
                                min_price = f"{min_price}，涨价: {increase_price}，小于或等于涨价阈值: {high_threshold}，或者同舱涨价，不报告警"
                        else:
                            logger.warning(f"比价平台报告与航班销售价持平")
                            min_price = "无"
                    else:
                        logger.warning(f"没有检索到航班{flight_no}数据")
                        min_price = "无"
                    await activity_order_queue.requeue(task=key)
                    message = f"劲旅订单：{order_id}，航班：{flight_no}，乘客票面价：{price_std}，销售价：{price_sell}，航班实时最低价：{min_price}"
                    logger.info(message)
                    return message
                else:
                    await activity_order_queue.requeue(task=key)
                    logger.warning(f"没有检索到航班{flight_no}数据")
            else:
                await activity_order_queue.requeue(task=key)
                raise RuntimeError(f"调用去哪儿fuwu的API响应异常，响应如：{str(response)}")
        else:
            await activity_order_queue.finish(task=key)
            logger.warning("超过订单查询有效期")
            return
    else:
        logger.warning("Redis队列中没有询价数据")
        return


async def fuwu_qunar_flight_price_comparison_local_executor(
        *, logger: Logger, qlv_domain: Optional[str] = None, qlv_protocol: Optional[str] = None, sleep: int = 60,
        timeout: Optional[int] = None, retry: Optional[int] = None, low_threshold: Optional[int] = None,
        high_threshold: Optional[int] = None, uuid: Optional[str] = None, headers: Optional[Dict[str, Any]] = None
) -> None:
    while True:
        logger.info(f"开始查询去哪儿fuwu平台航班数据进行比价流程......")
        try:
            await executor_fuwu_qunar_flight_price_comparison_task(
                logger=logger, timeout=timeout or config.timeout, retry=retry or config.retry, qlv_domain=qlv_domain,
                low_threshold=low_threshold or config.low_threshold, uuid=uuid or config.uuid, enable_log=True,
                high_threshold=high_threshold or config.high_threshold, headers=headers or config.headers,
                qlv_protocol=qlv_protocol
            )
        except (RuntimeError, EnvironmentError, Exception) as e:
            logger.error(e)
        logger.info(f"查询去哪儿fuwu平台航班数据进行比价流程结束，等待<{sleep}>秒后将重试")
        await asyncio.sleep(sleep)


def register(executor):
    @executor.register(name="fuwu_qunar_flight_price_comparison")
    async def fuwu_qunar_flight_price_comparison():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            "[fuwu_qunar_flight_price_comparison] running with executor params: %s" % executor_params)
        return await executor_fuwu_qunar_flight_price_comparison_task(
            logger=g.logger, uuid=executor_params.get("uuid") or config.uuid,
            headers=executor_params.get("headers") or config.headers,
            low_threshold=executor_params.get("low_threshold") or config.low_threshold,
            high_threshold=executor_params.get("high_threshold") or config.high_threshold,
            timeout=executor_params.get("timeout") or config.timeout,
            retry=executor_params.get("retry") or config.retry, enable_log=True,
            qlv_protocol=executor_params.get("qlv_protocol") or config.qlv_protocol,
            qlv_domain=executor_params.get("qlv_domain") or config.qlv_domain
        )


if __name__ == '__main__':
    from logging import INFO
    from log_tuils import setup_logger, get_log_dir

    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="fuwu_qunar_flight_price_comparison", log_level=INFO
    )
    try:
        asyncio.run(fuwu_qunar_flight_price_comparison_local_executor(logger=logger))
    except (KeyboardInterrupt, SystemExit, Exception):
        logger.warning("程序已经退出")
