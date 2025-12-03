# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     robot_message_template.py
# Description:  机器人消息模板
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
from datetime import datetime
from typing import Dict, Any, Optional
from http_helper.client.async_proxy import HttpClientFactory

message_api_config = {
    "protocol": "http",
    "address": "192.168.3.240:18090"
}


def get_current_dtstr() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")

def get_current_datetimestr() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def send_message_to_dingdin_robot(
        message: Dict[str, Any], message_type: str, robot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    message_http_client = HttpClientFactory(
        protocol=message_api_config.get('protocol'),
        domain=message_api_config.get('address'),
        timeout=10,
        retry=2,
        enable_log=True
    )
    json_data = {
        "message_type": message_type,
        "message": message,
        "robot": robot
    }
    return await message_http_client.request(
        method="post",
        url="/api/v1/agent/message/dingding/robot/send",
        json_data=json_data,
        is_end=True
    )


def get_ctrip_price_comparison_template(
        order_id: int, flight_no: str, price_std: float, price_sell: float, min_price: float, ctrip_url: str
) -> Dict[str, Any]:
    qlv_url = f"https://pekzhongqihl.qlv88.com/OrderProcessing/NewTicket_show/{order_id}?&r={get_current_dtstr()}"
    return {
        "title": f"航班【{flight_no}】价格有变动",
        "text": f"## 基本信息\n\n\n\n**通知时间**：{get_current_datetimestr()}\n\n**劲旅订单**：{order_id}\n\n**航班**：{flight_no}\n\n**乘客票面价**：{price_std}\n\n**乘客销售价**：{price_sell}\n\n**当前携程平台最低价**：{min_price}",
        "btnOrientation": "0",
        "btns": [
            {
                "title": "打开携程",
                "actionURL": ctrip_url
            },
            {
                "title": "打开劲旅",
                "actionURL": qlv_url
            }
        ]
    }

def get_fuwu_qunar_price_comparison_template(
        order_id: int, flight_no: str, price_std: float, price_sell: float, min_price: str, ctrip_url: str
) -> Dict[str, Any]:
    qlv_url = f"https://pekzhongqihl.qlv88.com/OrderProcessing/NewTicket_show/{order_id}?&r={get_current_dtstr()}"
    return {
        "title": f"航班【{flight_no}】价格有变动",
        "text": f"## 基本信息\n\n\n\n**通知时间**：{get_current_datetimestr()}\n\n**劲旅订单**：{order_id}\n\n**航班**：{flight_no}\n\n**乘客票面价**：{price_std}\n\n**乘客销售价**：{price_sell}\n\n**当前去哪儿平台最低价**：{min_price}",
        "btnOrientation": "0",
        "btns": [
            {
                "title": "打开去哪儿",
                "actionURL": ctrip_url
            },
            {
                "title": "打开劲旅",
                "actionURL": qlv_url
            }
        ]
    }
