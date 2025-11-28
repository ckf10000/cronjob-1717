# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     update_qlv_login_state.py
# Description:  更新劲旅登录状态
# Author:       ASUS
# CreateDate:   2025/11/28
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import json
import asyncio
from typing import Dict, Any
from playwright_stealth import Stealth
from jobs.redis_helper import redis_client
from qlv_helper.po.login_page import LoginPage
from playwright.async_api import async_playwright
from qlv_helper.controller.user_login import wechat_login
from qlv_helper.utils.stealth_browser import CHROME_STEALTH_ARGS, IGNORE_ARGS, USER_AGENT, viewport, setup_stealth_page


async def update_login_state(cache_expired_duration: int = 86400) -> str:
    login_state: Dict[str, Any] = await redis_client.get(key=redis_client.gen_qlv_login_state_key())
    if login_state:
        return "检测到劲旅平台登录状态未过期，暂时无需更新"
    login_url: str = "https://pekzhongqihl.qlv88.com/Home/Login"
    timeout: float = 5.0
    retry: int = 3
    # 创建 stealth 配置
    stealth = Stealth(
        navigator_webdriver=True,  # 隐藏 webdriver
        navigator_plugins=True,  # 修改插件
        navigator_languages=True,  # 修改语言
        navigator_platform=True,  # 修改平台
        navigator_user_agent=False,  # 修改 UA
        script_logging=False,  # 生产环境关闭日志
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=r"D:\workspace\automation_profile",
            channel="chrome",  # 重点！！！启动真正的 Chrome
            headless=True,  # 确保显示浏览器窗口
            args=CHROME_STEALTH_ARGS,
            ignore_default_args=IGNORE_ARGS,
            user_agent=USER_AGENT,
            viewport=viewport
        )
        page = await browser.new_page()

        # 应用 stealth 插件
        await stealth.apply_stealth_async(page_or_context=page)
        await setup_stealth_page(page=page)

        await page.goto(login_url)
        await asyncio.sleep(1)

        login_po = LoginPage(page=page)
        is_success, result = await wechat_login(browser=browser, login_po=login_po, timeout=timeout, retry=retry)
        if is_success is True:
            # 不指定 path，Playwright 会返回 JSON 字符串
            state_json = await browser.storage_state()
            await redis_client.set(
                key=redis_client.gen_qlv_login_state_key(), value=state_json, ex=cache_expired_duration
            )

        await browser.close()

        if is_success is True:
            return "检测到劲旅平台登录状态已过期，并已完成更新"
        else:
            return f"检测到劲旅平台登录状态已过期，{result}"


def register(executor):
    @executor.register(name="update_qlv_login_state")
    async def update_qlv_login_state():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[fetch_flight_order_to_redis_by_qlv] running with executor params: %s" % executor_params)
        return await update_login_state(cache_expired_duration=executor_params.get("cache_expired_duration", 86400))


if __name__ == '__main__':
    from time import sleep
    from datetime import datetime

    slp = 120
    try:
        while True:
            try:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 劲旅平台登录状态是否过期检测中...")
                asyncio.run(update_login_state())
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {slp}秒后继续检测")
                sleep(slp)
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {e}")
    except (KeyboardInterrupt, Exception):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测已退出...")
