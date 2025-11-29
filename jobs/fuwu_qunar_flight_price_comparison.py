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
import logging
from typing import Optional, Dict, Any
from http_helper.client.async_proxy import HttpClientFactory
from jobs.redis_helper import redis_client, activity_order_queue
from jobs.robot_message_template import get_fuwu_qunar_price_comparison_template, send_message_to_dingdin_robot

"""
比价逻辑
1. 从redis队列尾部中取出即将要比价的订单key，从K,V存储中取出订单详情
2. 详情有值，调用去哪儿平台API比价；无值则扔掉key，直接结束任务
3. 详情有值，订单key插入redis队列队首，无值则忽略此步骤
"""

fuwu_api_config = {
    "protocol": "https",
    "address": "fuwu.qunar.com"
}


async def fetch_tts_agent_tool_total(
        flight_no: str, dpt: str, arr: str, flight_date: str, uuid: str = None, headers: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    order_http_client = HttpClientFactory(
        protocol=fuwu_api_config.get('protocol'),
        domain=fuwu_api_config.get('address'),
        timeout=10,
        retry=0,
        enable_log=True
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
    response = await order_http_client.request(
        method="get",
        url="/tts/agent/tool/statistics/bidding",
        headers=headers_default,
        params=params_data,
        is_end=True
    )
    return response


async def flight_price_comparison(logger: logging.Logger, uuid: str = None, headers: Dict[str, Any] = None) -> str:
    # 1. 恢复processing队列中的任务
    await activity_order_queue.recover()
    # 2. 从队尾取出（FIFO）
    key = await activity_order_queue.pop()
    if key:
        cache_data = await redis_client.get(key)
        if cache_data:
            order_id = cache_data.get("id")
            flights = cache_data.get("flights")
            peoples = cache_data.get("peoples")
            # 只取第一段航程的数据作为比价的检索数据
            flight = flights[0] if isinstance(flights, list) and len(flights) > 0 else dict()
            people = peoples[0] if isinstance(peoples, list) and len(peoples) > 0 else dict()
            flight_no = flight.get("flight_no")
            price_std = people.get("price_std")
            price_sell = people.get("price_sell")
            city_dep = flight.get("city_dep").strip() if flight.get("city_dep") else ""
            city_arr = flight.get("city_arr").strip() if flight.get("city_arr") else ""
            code_dep = flight.get("code_dep").strip() if flight.get("code_dep") else ""
            code_arr = flight.get("code_arr").strip() if flight.get("code_arr") else ""
            dep_date = redis_client.iso_to_standard_datestr(datestr=flight.get("dat_dep"), time_zone_step=8)
            response = await fetch_tts_agent_tool_total(
                flight_no=flight_no, dpt=code_dep, arr=code_arr, flight_date=dep_date, uuid=uuid, headers=headers
            )
            data = response.get("data") or dict()
            if data and isinstance(data, dict) and response.get("data").get("orderList"):
                order_list = data.get("orderList") or list()
                if order_list:
                    logger.info(f"[fuwu_qunar_flight_price_comparison] 已检索到航班{flight_no}数据")
                    url = f"https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport={code_dep}&searchArrivalAirport={code_arr}&searchDepartureTime={dep_date}&searchArrivalTime={dep_date}&nextNDays=0&startSearch=true&fromCode={city_dep}&toCode={city_arr}&from=flight_dom_search&lowestPrice=null"
                    # 排序（默认升序）,reverse=False, sellPrice 外放底价， sellFloorPrice 外放追价底价
                    sell_price_list = [x for x in order_list if price_sell > x.get("sellPrice") > 0]
                    wiew_price_list = [x for x in order_list if price_sell > x.get("maxViewPrice") > 0]
                    if sell_price_list or wiew_price_list:
                        if sell_price_list:
                            sell_price_list.sort(key=lambda x: x["sellPrice"])
                            min_price = sell_price_list[0]["sellPrice"]
                        else:
                            wiew_price_list.sort(key=lambda x: x["maxViewPrice"])
                            min_price = wiew_price_list[0]["maxViewPrice"]
                        action_card_message = get_fuwu_qunar_price_comparison_template(
                            order_id=order_id, flight_no=flight_no, price_std=price_std,
                            price_sell=price_sell, min_price=min_price, ctrip_url=url
                        )
                        await send_message_to_dingdin_robot(
                            message=action_card_message, message_type="actionCard"
                        )
                    else:
                        min_price = "高于销售价"
                else:
                    logger.warning(f"[fuwu_qunar_flight_price_comparison] 没有检索到航班{flight_no}数据")
                    min_price = "无"
                message = f"[fuwu_qunar_flight_price_comparison] 订单：{order_id}，航班：{flight_no}，乘客票面价：{price_std}，销售价：{price_sell}，航班实时最低价：{min_price}"
                logger.info(message)
            else:
                message = str(response)
                logger.error(message)
            await activity_order_queue.requeue(task=key)
            return message
        else:
            await activity_order_queue.finish(task=key)
            return "超过订单查询有效期"
    else:
        return "Redis队列中没有询价数据"


def register(executor):
    @executor.register(name="fuwu_qunar_flight_price_comparison")
    async def fuwu_qunar_flight_price_comparison():
        from pyxxl.ctx import g
        executor_params = g.xxl_run_data.executorParams if isinstance(
            g.xxl_run_data.executorParams, dict
        ) else json.loads(g.xxl_run_data.executorParams)
        g.logger.info(
            "[fuwu_qunar_flight_price_comparison] running with executor params: %s" % executor_params)
        return await flight_price_comparison(
            logger=g.logger, uuid=executor_params.get("uuid"), headers=executor_params.get("headers")
        )


# 模块内不要直接调用 asyncio.run()，只提供 async 函数/async generator，让调用方决定如何调度。
# 异步环境已经存在就直接 await，否则可以 asyncio.run()
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("root")
    # asyncio.run(fetch_tts_agent_tool_total(flight_no="HU7389", dpt="SZX", arr="HGH", flight_date="2025-12-17"))
    asyncio.run(flight_price_comparison(logger=logger))
