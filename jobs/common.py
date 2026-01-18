# -*- coding: utf-8 -*-
"""
# ---------------------------------------------------------------------------------------------------------
# ProjectName:  cronjob-1717
# FileName:     common.py
# Description:  公共模块
# Author:       ASUS
# CreateDate:   2025/12/25
# Copyright ©2011-2025. Hunan xxxxxxx Company limited. All rights reserved.
# ---------------------------------------------------------------------------------------------------------
"""
import platform
import jobs.config as config
from datetime import datetime
from urllib.parse import quote
from log_utils import get_screenshot_dir
from typing import Literal, Optional, Dict
from playwright_helper.middlewares.stealth import *
from playwright_helper.libs.browser_pool import BrowserPool
from http_helper.client.async_proxy import HttpClientFactory
from playwright_helper.libs.executor import PlaywrightBrowserExecutor

if platform.system() == 'Windows':
    headless = False
else:
    headless = True


def get_browser_pool(logger: Logger) -> BrowserPool:
    return BrowserPool(
        size=2,
        logger=logger,
        headless=headless,
        args=CHROME_STEALTH_ARGS,
        ignore_default_args=IGNORE_ARGS,
    )


def get_playwright_executor(
        *, logger: Logger, retry: int, pool: BrowserPool, mode: Literal["persistent", "storage"] = "storage"
) -> PlaywrightBrowserExecutor:
    return PlaywrightBrowserExecutor(
        mode=mode,
        logger=logger,
        retries=retry,
        middlewares=[stealth_middleware],
        screenshot_dir=get_screenshot_dir(),
        browser_pool=pool,
        viewport=viewport,
        user_agent=USER_AGENT
    )


async def fetch_tts_agent_tool_total(
        *, flight_no: str, dpt: str, arr: str, flight_date: str, timeout: int = 60, retry: int = 0,
        enable_log: bool = True, uuid: Optional[str] = None, headers: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    order_http_client = HttpClientFactory(
        protocol=config.fuwu_protocol,
        domain=config.fuwu_domain,
        timeout=timeout,
        retry=retry,
        enable_log=enable_log
    )
    uuid_default = "FYwHxRQZw8a4WcWF"
    if uuid:
        uuid_default = uuid
    params_data = {
        "flightNo": flight_no,
        "dpt": dpt,
        "arr": arr,
        "flightDate": flight_date,
        "quotedBoothType": "activity",  # all 全部，activity 活动展位
        "currentPage": 1,
        "domain": "snz.trade.qunar.com",
        "type": "0",
        "UUID": uuid_default
    }
    headers_default = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,eu;q=0.7",
        "cookie": "QN1=0000f60027c476e88968afdc; ctt_june=1683616182042##iK3wWS2%2BWhPwawPwa%3DD%3DaRWTWSGTaRX8EPXNX%3DGDaKHTaSHRXsX%2BERvnW2DmiK3siK3saKgOWRDsasj%2BWs2sWhPwaUvt; QN271AC=register_pc; QN271SL=9870226df602ba5494a455d0e0708f05; QN271RC=9870226df602ba5494a455d0e0708f05; _q=U.upxypdm9971; csrfToken=E7tBvj3NiRsbCGVdsfnDeCHsK1LkpEcS; _s=s_PUZMBFN4D2M5NZ6YVMY63BUBFM; _t=29511668; _v=r0tRrsBjuek5IzFXjfPp1jQxUlOlvjfYZ35hpRAGKtTuLN21Z2lI_n8C2uX3vTvUbdKi4HMjgh2lbaN-kY2TMQspIGSTDoQv7yiLmkPcpaiMdNKT2eMJ7I_xTdAop6mYfgjX1OGAJT2JVFsm2HjScgMFP8qUe2a6iYY3wDR7AjoI; QN43=2; QN42=%E5%8E%BB%E5%93%AA%E5%84%BF%E7%94%A8%E6%88%B7; _mdp=CA57CD58643078AD14624767BBCBC484; _uf=upxypdm9971; QN238=zh_cn; QN74=snz.trade.qunar.com; QN601=c38617eaa4c7e842909b227ea7292ca1; QN166=upxypdm9971; JSESSIONID=D7472593B6F4153ED2D344EE2F65D5F6; QN300=organic; QN99=9858; qunar-assist={%22version%22:%2220211215173359.925%22%2C%22show%22:false%2C%22audio%22:false%2C%22speed%22:%22middle%22%2C%22zomm%22:1%2C%22cursor%22:false%2C%22pointer%22:false%2C%22bigtext%22:false%2C%22overead%22:false%2C%22readscreen%22:false%2C%22theme%22:%22default%22}; QN44=upxypdm9971; _i=DFiEuMRwwwA7GNHe_KQqr7zLa4Aw; QN269=5164ED90CA8711F09B94DA58E85CC84C; fid=65c1ecdb-9212-4182-bc1a-4b7818560a21; QN48=0000ed002f1076e89cf076d6; quinn=fb0b471ca29355065be96e771625a95b837c075ed49b1ded855bdb679e6ddfe44e1a1adf268e39687a1c59fe4c1f2662; ctf_june=1683616182042##iK3waKD8auPwawPwasXwW2fIXPkTaKGIVKoTW2ERXK38WPkTa2anER0DXK3miK3siK3saKgOWRDsWRasWstwWUPwaUvt; QN621=fr%3Dflight_dom_search; QN267=1313058751b65eff5b; _vi=xbQv-vsXKmc-k2cqghNogrKFERzTchdrNjHqXOPwSj8b8UHZ0Mp69r3-d2n3WNugJzoAHYzAgvOjwGROX3EDEMTfbOywjyXez2tqzhbrslWkuRJfAQPlTAcUH-iWETELpr6e5ardYqpUon1i_6zg_ghKt29TYBNE7dcG06UYU4y-; ariaDefaultTheme=undefined; QN271=1f5a5a32-5049-4d4b-b279-1e263137f94b; QN668=51%2C57%2C56%2C54%2C51%2C53%2C59%2C57%2C59%2C59%2C59%2C54%2C52; 11344=1722403391463##iK3wWStsWwPwawPwa%3DPAWRjsVRiGas0haKjwVRkDX2XsaKfDVDGRXSfhVRP8iK3siK3saKgOWRD%3DaKv8aKj8WuPwaUvt; 11536=1722403391463##iK3wWKP%3DawPwawPwa%3DEhaSP%3DEK3sa2GIXsfDa%3DaNaStwaKv8VKaOWRfGaSHhiK3siK3saKgOWRDsWRXwVKjOaUPwaUvt; cs_june=c091f463fb07c8bc8a02ce4b81284874965af756159498ae326815441b992da8d70a08cfff3bcd9e1a84baaba6534e783c9415d147e98348e7d6e4160559ab9fb17c80df7eee7c02a9c1a6a5b97c11797a62b821811266ae96f76614c9c001895a737ae180251ef5be23400b098dd8ca"
    }
    if headers and isinstance(headers, dict):
        headers_default.update(headers)
    return await order_http_client.request(
        method="get",
        url="/tts/agent/tool/statistics/bidding",
        headers=headers_default,
        params=params_data,
        is_end=True
    )


def get_current_dtstr() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def get_current_datetimestr() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def send_message_to_dingdin_robot(
        message: Dict[str, Any], message_type: str, robot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    message_http_client = HttpClientFactory(
        protocol=config.robot_protocol,
        domain=config.robot_domain,
        timeout=int(config.timeout),
        retry=config.retry,
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


def get_dingding_pc_slide_url(url: str) -> str:
    return "dingtalk://dingtalkclient/page/link?url=" + quote(url, safe='') + "&pc_slide=false"


def get_fuwu_qunar_price_comparison_template(
        order_id: int, flight_no: str, price_std: float, price_sell: float, min_price: str, qunar_url: str,
        order_cabin: str, ota_cabin: str, source_ota: str, dat_dep: str, qlv_protocol: str, qlv_domain: str
) -> Dict[str, Any]:
    qlv_url = f"{qlv_protocol}://{qlv_domain}/OrderProcessing/NewTicket_show/{order_id}?&r={get_current_dtstr()}"
    qlv_url = get_dingding_pc_slide_url(url=qlv_url)
    qunar_url = get_dingding_pc_slide_url(url=qunar_url)
    return {
        "title": f"航班【{flight_no}】价格有变动",
        "text": f"## 基本信息\n\n\n\n**通知时间**：{get_current_datetimestr()}\n\n**劲旅订单**：{order_id}\n\n**订单来源**：{source_ota}\n\n**航班**：{flight_no}\n\n**起飞时间**：{dat_dep}\n\n**乘客舱位**：{order_cabin}\n\n**乘客票面价**：{price_std}\n\n**乘客销售价**：{price_sell}\n\n**去哪儿外放舱位**：{ota_cabin}\n\n**去哪儿最低价**：{min_price}",
        "btnOrientation": "0",
        "btns": [
            {
                "title": "打开去哪儿",
                "actionURL": qunar_url
            },
            {
                "title": "打开劲旅",
                "actionURL": qlv_url
            }
        ]
    }
