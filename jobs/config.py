# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     config.py
# Description:  配置模块
# Author:       ASUS
# CreateDate:   2025/12/26
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
from typing import List, Dict, Any

qlv_protocol: str = "https"
qlv_domain: str = "pekzhongqihl.qlv88.com"
qlv_user_id: str = "周汗林"
qlv_user_password: str = "pass@123aA"
login_attempt: int = 100
discard_state: List[str] = ["出票完成", "出票成功", "已作废"]
qlv_user_login_state_expired_duration: int = 3600 * 24

retry: int = 0
timeout: float = 60
last_minute_threshold: int = 60
semaphore: int = 10

low_threshold: int = 10
high_threshold: int = 20
fuwu_protocol: str = "https"
fuwu_domain: str = "fuwu.qunar.com"
uuid: str = "FYwHxRQZw8a4WcWF"
headers: Dict[str, Any] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,eu;q=0.7"
}

robot_protocol: str = "http"
robot_domain: str = "192.168.3.240:18090"

baidu_api_key: str = "qYdprRhqgrJRkIV0WT2xdm2o"
baidu_secret_key: str = "7yOMmGkDYeE6u2SXOyHeYQXzCTS26rsT"
