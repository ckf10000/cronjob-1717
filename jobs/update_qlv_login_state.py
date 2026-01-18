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
from logging import Logger
import jobs.config as config
from aiohttp import CookieJar
from typing import Dict, Any, Optional
from playwright_stealth import Stealth
from qlv_helper.po.login_page import LoginPage
from playwright.async_api import async_playwright
from playwright_helper.libs.executor import RunResult
from qlv_helper.controller.main_page import open_main_page
from qlv_helper.controller.user_login import username_login
from qlv_helper.controller.wechat_login import wechat_login
from jobs.common import get_browser_pool, get_playwright_executor
from qlv_helper.controller.main_page import get_main_info_with_http
from log_utils import setup_logger, get_screenshot_dir, get_log_dir
from jobs.redis_utils import redis_client_0, redis_client_1, gen_qlv_login_state_key
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from qlv_helper.utils.stealth_browser import CHROME_STEALTH_ARGS, IGNORE_ARGS, USER_AGENT, viewport, setup_stealth_page

"""
更新劲旅平台登录状态逻辑
1. 从redis中获取登录状态信息
2. 利用状态信息，打开订单详情页，看看能否正常返回详情页数据， 能返回说明登录状态有效，任务完成
3. 若不能返回，则执行一次登录过程，若过程执行失败，抛异常
4. 若过程执行成功，将状态数据写入redis，任务完成
"""


async def executor_update_qlv_login_state_with_wechat_task(
        *, logger: Logger, qlv_user_id: str, qlv_domain: str, qlv_protocol: str, cache_expired_duration: int,
        timeout: float, retry: int, **kwargs: Any
) -> Optional[str]:
    login_state: Dict[str, Any] = await redis_client_0.get(key=gen_qlv_login_state_key(user_id=qlv_user_id))
    response: [str, Any] = await get_main_info_with_http(
        domain=qlv_domain, protocol=qlv_protocol, retry=retry, timeout=int(timeout), enable_log=True,
        cookie_jar=CookieJar(), playwright_state=login_state
    )
    if response.get('code') == 200 and "中企航旅航空科技有限公司 劲旅系统" in response.get('message').strip():
        logger.warning(f"劲旅用户<{qlv_user_id}>登录状态有效，任务跳过")
        return
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
            await redis_client_0.set(
                key=gen_qlv_login_state_key(user_id=qlv_user_id), value=state_json, ex=cache_expired_duration
            )
            await redis_client_1.set(
                key=gen_qlv_login_state_key(user_id=qlv_user_id), value=state_json, ex=cache_expired_duration
            )
        await browser.close()

        if is_success is True:
            logger.info(f"劲旅用户<{qlv_user_id}>，微信认证方式登录成功，并已完成缓存数据更新")
            return "任务执行成功"
        else:
            raise RuntimeError(f"劲旅用户<{qlv_user_id}>，微信认证方式登录失败，原因：{result}")


async def executor_update_qlv_login_state_with_username_task(
        *, logger: Logger, qlv_protocol: str, qlv_domain: str, qlv_user_id: str, qlv_user_password: str,
        cache_expired_duration: int, api_key: str, secret_key: str, timeout: float = 20.0, retry: int = 0,
        attempt: int = 100, **kwargs: Any
) -> Optional[str]:
    playwright_state = await redis_client_0.get(key=gen_qlv_login_state_key(user_id=qlv_user_id))
    pool = get_browser_pool(logger=logger)
    executor = get_playwright_executor(logger=logger, retry=retry, pool=pool)
    await executor.start()
    if playwright_state:
        result: RunResult = await executor.run(
            callback=open_main_page, storage_state=playwright_state, qlv_protocol=qlv_protocol, qlv_domain=qlv_domain,
            timeout=timeout
        )
        if result.success is True:
            logger.warning(f"劲旅用户<{qlv_user_id}>，当前登录状态有效，本次任务就就此跳过")
            # 进程退出时关闭
            await pool.stop()
            await executor.stop()
            return
        else:
            logger.error(result.error)

    result: RunResult = await executor.run(
        callback=username_login, username=qlv_user_id, password=qlv_user_password, qlv_protocol=qlv_protocol,
        qlv_domain=qlv_domain, screenshot_dir=get_screenshot_dir(), timeout=timeout, api_key=api_key,
        secret_key=secret_key, attempt=attempt
    )
    # 进程退出时关闭
    await pool.stop()
    await executor.stop()

    if result.result and isinstance(result.result, dict):
        await redis_client_0.set(
            key=gen_qlv_login_state_key(user_id=qlv_user_id), value=result.result, ex=cache_expired_duration
        )
        await redis_client_1.set(
            key=gen_qlv_login_state_key(user_id=qlv_user_id), value=result.result, ex=cache_expired_duration
        )
        msg: str = "任务执行成功"
        logger.info(msg)
        return msg
    else:
        raise result.error


async def update_qlv_login_state_local_executor(
        *, logger: Logger, sleep: int = 60, qlv_user_id: Optional[str] = None, domain: Optional[str] = None,
        protocol: Optional[str] = None, timeout: Optional[int] = None, retry: Optional[int] = None,
        cache_expired_duration: Optional[int] = None, qlv_user_password: Optional[str] = None,
        api_key: Optional[str] = None, secret_key: Optional[str] = None, attempt: Optional[int] = None, **kwargs: Any
):
    while True:
        logger.info(f"劲旅平台登录状态是否过期检测中...")
        try:
            # await executor_update_qlv_login_state_with_wechat_task(
            #     logger=logger, qlv_user_id=qlv_user_id or config.qlv_user_id, qlv_domain=domain or config.qlv_domain,
            #     qlv_protocol=protocol or config.qlv_protocol, timeout=timeout or config.timeout,
            #     retry=retry or 3,
            #     cache_expired_duration=cache_expired_duration or config.qlv_user_login_state_expired_duration
            # )
            await executor_update_qlv_login_state_with_username_task(
                logger=logger, qlv_user_id=qlv_user_id or config.qlv_user_id, qlv_domain=domain or config.qlv_domain,
                qlv_protocol=protocol or config.qlv_protocol, timeout=timeout or config.timeout,
                secret_key=secret_key or config.baidu_secret_key, retry=retry or config.retry,
                qlv_user_password=qlv_user_password or config.qlv_user_password,
                api_key=api_key or config.baidu_api_key, attempt=attempt or config.login_attempt,
                cache_expired_duration=cache_expired_duration or config.qlv_user_login_state_expired_duration
            )
        except (PlaywrightError, PlaywrightTimeoutError, RuntimeError, EnvironmentError, Exception) as e:
            logger.error(e)
        logger.info(f"劲旅平台登录状态是否过期检测流程结束，等待<{sleep}>秒后将重试")
        await asyncio.sleep(sleep)


def register(executor):
    @executor.register(name="update_qlv_login_state")
    async def update_qlv_login_state():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(f"[update_qlv_login_state] running with executor params: {executor_params}")
        return await executor_update_qlv_login_state_with_username_task(
            logger=g.logger,
            qlv_domain=executor_params.get("qlv_domain") or config.qlv_domain,
            qlv_protocol=executor_params.get("qlv_protocol") or config.qlv_protocol,
            qlv_user_id=executor_params.get("qlv_user_id") or config.qlv_user_id,
            qlv_user_password=executor_params.get("qlv_user_password") or config.qlv_user_login_state_expired_duration,
            cache_expired_duration=executor_params.get(
                "cache_expired_duration") or config.qlv_user_login_state_expired_duration,
            api_key=executor_params.get("api_key") or config.baidu_api_key,
            secret_key=executor_params.get("secret_key") or config.baidu_secret_key,
            retry=executor_params.get("retry") or config.retry,
            timeout=executor_params.get("timeout") or config.timeout,
            attempt=executor_params.get("attempt") or config.login_attempt
        )


if __name__ == '__main__':
    from logging import INFO

    logger = setup_logger(
        logs_dir=get_log_dir(), file_name="update_qlv_login_state", log_level=INFO
    )
    try:
        asyncio.run(update_qlv_login_state_local_executor(logger=logger, sleep=60))
    except (KeyboardInterrupt, SystemExit, Exception):
        logger.warning("程序已经退出")
