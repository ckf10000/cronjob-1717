# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     redis_helper.py
# Description:  redis帮助模块
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from redis_helper.client import AsyncRedisHelper
from redis_helper.set_helper import AsyncReliableQueue
from playwright_helper.utils.type_utils import safe_convert_advanced

standard_date_format = "%Y-%m-%d %H:%M:%S"


def gen_qlv_flight_order_key_prefix(
        *, dep_city: str = None, arr_city: str = None, dep_date: str = None, flight_no: str = None, cabin: str = None,
        extend: str = None
) -> str:
    # 格式： flight:order:[平台ID]:[departureCityCode]:[arrivalCityCode]:[日期]:[flightNo]:[cabin]:[平台单号]
    # 如：flight:order:qlv:CAN:WUS:2025-12-01:SC4674:S:153471
    li = ["flight", "order", "qlv"]
    if dep_city:
        if isinstance(dep_city, str) is False:
            dep_city = str(dep_city)
        li.append(dep_city)
    if arr_city:
        if isinstance(arr_city, str) is False:
            arr_city = str(arr_city)
        li.append(arr_city)
    if dep_date:
        if isinstance(dep_date, str) is False:
            dep_date = str(dep_date)
        dep_date = dep_date.replace(" ", "T")
        dep_date = dep_date.replace(":", "/")
        li.append(dep_date)
    if flight_no:
        if isinstance(flight_no, str) is False:
            flight_no = str(flight_no)
        li.append(flight_no)
    if cabin:
        if isinstance(cabin, str) is False:
            cabin = str(cabin)
        li.append(cabin)
    if extend:
        if isinstance(extend, str) is False:
            extend = str(extend)
        li.append(extend)
    return ":".join(li)

def qlv_flight_order_key_convert_dict(key: str) -> Dict[str, Any]:
    try:
        key_slice = key.split(":")
        dep_date = key_slice[5]
        dep_date = dep_date.replace("T", " ")
        dep_date = dep_date.replace("/", ":")
        data = {
            "dep_city": key_slice[3],
            "arr_city": key_slice[4],
            "dep_date": dep_date,
            "flight_no": key_slice[6],
            "cabin": key_slice[7],
            "extend": safe_convert_advanced(value=key_slice[8])
        }
        if len(key_slice) > 9:
            data["extend+"] = ":".join(key_slice[9:])
        return data
    except (IndexError, ValueError, Exception) as e:
        print(e)
        return dict()


def gen_qlv_flight_activity_order_list_key() -> str:
    return ":".join(["flight", "order", "qlv", "activity"])


def gen_qlv_flight_order_state_list_key() -> str:
    return ":".join(["flight", "order", "qlv", "state"])


def iso_to_standard_datetimestr(datestr: str, time_zone_step: int) -> str:
    """iso(2024-04-21T04:20:00Z)格式转 标准的时间格式(2024-01-01 00:00:00)"""
    dt_str = "{} {}".format(datestr[:10], datestr[11:-1])
    dt = datetime.strptime(dt_str, standard_date_format)
    dt_step = dt + timedelta(hours=time_zone_step)
    return dt_step.strftime(standard_date_format)


def iso_to_standard_datestr(datestr: str, time_zone_step: int) -> str:
    """iso(2024-04-21T04:20:00Z)格式转 标准的时间格式(2024-01-01)"""
    return iso_to_standard_datetimestr(datestr=datestr, time_zone_step=time_zone_step)[:10]


def gen_qlv_login_state_key(extend: Optional[str] = None) -> str:
    li = ["qlv", "login", "state"]
    if extend:
        if isinstance(extend, str) is False:
            extend = str(extend)
        li.append(extend)
    return ":".join(li)


def general_key_vid(last_time_ticket: str) -> int:
    last_time = datetime.strptime(last_time_ticket, '%Y-%m-%d %H:%M:%S')
    delta = last_time - datetime.now()
    seconds = delta.total_seconds()
    if seconds >= 0:
        return int(seconds)
    else:
        return 86400


redis_client = AsyncRedisHelper(host='192.168.3.240', port=6379, db=0, password="Admin@123", decode_responses=True)
redis_client_ = AsyncRedisHelper(host='192.168.3.240', port=6379, db=1, password="Admin@123", decode_responses=True)
activity_order_queue = AsyncReliableQueue(redis=redis_client.redis, key=gen_qlv_flight_activity_order_list_key())
order_state_queue = AsyncReliableQueue(redis=redis_client.redis, key=gen_qlv_flight_order_state_list_key())
