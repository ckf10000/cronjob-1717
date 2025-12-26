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
import traceback
import jobs.config as config
from typing import Dict, Any
from datetime import datetime
from aiohttp import CookieJar
from playwright_stealth import Stealth
from qlv_helper.po.login_page import LoginPage
from playwright.async_api import async_playwright
from qlv_helper.controller.user_login import wechat_login
from qlv_helper.controller.main_page import get_main_info_with_http
from jobs.redis_utils import redis_client, redis_client_, gen_qlv_login_state_key
from qlv_helper.utils.stealth_browser import CHROME_STEALTH_ARGS, IGNORE_ARGS, USER_AGENT, viewport, setup_stealth_page

"""
更新劲旅平台登录状态逻辑
1. 从redis中获取登录状态信息
2. 利用状态信息，打开订单详情页，看看能否正常返回详情页数据， 能返回说明登录状态有效，任务完成
3. 若不能返回，则执行一次登录过程，若过程执行失败，抛异常
4. 若过程执行成功，将状态数据写入redis，任务完成
"""


async def update_login_state(domain: str = "pekzhongqihl.qlv88.com", protocol: str = "https",
                             user_id: str = config.qlv_user_id, cache_expired_duration: int = 86400) -> str:
    login_state: Dict[str, Any] = await redis_client.get(key=gen_qlv_login_state_key(extend=user_id))
    timeout: int = 5
    retry: int = 3
    response: [str, Any] = await get_main_info_with_http(
        domain=domain, protocol=protocol, retry=retry, timeout=timeout, enable_log=True,
        cookie_jar=CookieJar(), playwright_state=login_state
    )
    if response.get('code') == 200 and "中企航旅航空科技有限公司 劲旅系统" in response.get('message').strip():
        string = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 劲旅平台登录状态有效，任务跳过"
        return string
    login_url: str = "https://pekzhongqihl.qlv88.com/Home/Login"
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
                key=gen_qlv_login_state_key(extend=user_id), value=state_json, ex=cache_expired_duration
            )
            await redis_client_.set(
                key=gen_qlv_login_state_key(extend=user_id), value=state_json, ex=cache_expired_duration
            )
        await browser.close()

        if is_success is True:
            return "[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到劲旅平台登录状态已过期，并已完成更新"
        else:
            raise RuntimeError(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到劲旅平台登录状态已过期，{result}")


async def main_loop():
    slp = 120

    while True:
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 劲旅平台登录状态是否过期检测中...")
            result = await update_login_state()
            print(result)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {slp}秒后继续检测")
            await asyncio.sleep(delay=slp)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {traceback.format_exc()}")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {e}")


def register(executor):
    @executor.register(name="update_qlv_login_state")
    async def update_qlv_login_state():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            f"[fetch_flight_order_to_redis_by_qlv] running with executor params: %s" % executor_params)
        return await update_login_state(
            domain=executor_params.get("domain", "pekzhongqihl.qlv88.com"),
            protocol=executor_params.get("protocol", "https"),
            cache_expired_duration=executor_params.get("cache_expired_duration", 86400)
        )


if __name__ == '__main__':
    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, Exception):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测已退出...")
