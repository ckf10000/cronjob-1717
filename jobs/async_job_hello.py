# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     async_job_hello.py
# Description:  异步测试任务
# Author:       ASUS
# CreateDate:   2025/11/24
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import asyncio


def register(executor):
    @executor.register(name="async_job")
    async def async_job(*args, **kwargs):
        from pyxxl.ctx import g
        g.logger.info(f"[async_job] running with executor params: %s" % g.xxl_run_data.executorParams)
        await asyncio.sleep(1)
        return "async done"
