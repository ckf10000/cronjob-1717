# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     sync_job_hello.py
# Description:  同步测试任务
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""


def register(executor):
    @executor.register(name="sync_job")
    def sync_job(*args, **kwargs):
        from pyxxl.ctx import g
        g.logger.info(f"[sync_job] running with args params: {args}, kwargs params: {kwargs}")
        return "sync done"
