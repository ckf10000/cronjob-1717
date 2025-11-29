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
import json
import redis.asyncio as redis
from typing import Any, Union, Optional
from datetime import datetime, timedelta

standard_date_format = "%Y-%m-%d %H:%M:%S"


class AsyncRedisHelper:
    def __init__(self, **kwargs):
        self._r = redis.Redis(**kwargs)

    @property
    def redis(self) -> redis.Redis:
        return self._r

    async def set(self, key: str, value: Any, ex: Optional[int] = None, px: Optional[int] = None, **kwargs):
        """
        写入redis
        key: redis key
        value: str, dict, list
        ex: expire time in seconds
        px: expire time in milliseconds
        kwargs: 其他 redis set 参数
        """
        # 如果是 dict/list，序列化成 json
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        # str 或其他类型直接存
        await self._r.set(key, value, ex=ex, px=px, **kwargs)

    async def get(self, key: str) -> Union[str, dict, list, None]:
        val = await self._r.get(key)
        if val is None:
            return None
        try:
            # 尝试反序列化 json
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            # 不是 json 就直接返回字符串
            return val

    async def expire(self, key: str, expire: int):
        """ 为已存在的 key 设置过期时间"""
        await self._r.expire(name=key, time=expire)

    async def ttl(self, key: str) -> int:
        """检查剩余时间"""
        return await self._r.ttl(name=key)

    async def scan_keys_by_prefix(self, prefix: str):
        cursor = 0
        keys = []
        pattern = f"{prefix}*"

        while True:
            cursor, batch = await self._r.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    async def delete(self, key: str):
        await self._r.delete(key)

    async def close(self):
        await self._r.close()
        await self._r.connection_pool.disconnect()

    @staticmethod
    def gen_qlv_flight_order_key_prefix(dep_city: str = None, arr_city: str = None, dep_date: str = None,
                                        extend: str = None) -> str:
        # 格式： flight:order:[平台ID]:[departureCityCode]:[arrivalCityCode]:[日期]:[平台单号]
        # 如：flight:order:qlv:szx:hgh:2025-12-01:153471
        li = ["flight", "order", "qlv"]
        if dep_city:
            if isinstance(dep_city, str) is False:
                dep_city = str(dep_city)
            li.append(dep_city.lower())
        if arr_city:
            if isinstance(arr_city, str) is False:
                arr_city = str(arr_city)
            li.append(arr_city.lower())
        if dep_date:
            if isinstance(dep_date, str) is False:
                dep_date = str(dep_date)
            li.append(dep_date)
        if extend:
            if isinstance(extend, str) is False:
                extend = str(extend)
            li.append(extend)
        return ":".join(li)

    @staticmethod
    def gen_qlv_flight_activity_order_list_key() -> str:
        return ":".join(["flight", "order", "qlv", "activity"])

    @staticmethod
    def gen_qlv_flight_order_state_list_key() -> str:
        return ":".join(["flight", "order", "qlv", "state"])

    async def lpush(self, key: str, value: Any) -> bool:
        """
        将元素插入到 Redis 列表的头部
        key: redis key
        value: str, dict, list
        """
        # 如果是 dict/list，序列化成 json
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        # 将元素推入列表头部
        await self._r.lpush(key, value)
        return True

    async def rpop(self, key: str) -> Union[str, dict, list, None]:
        """
        从 Redis 列表的尾部取出元素
        key: redis key

        返回值：返回列表中的一个元素，可能是 JSON 格式或者普通字符串
        """
        val = await self._r.rpop(key)
        if val is None:
            return None
        try:
            # 尝试反序列化 json
            return json.loads(val)
        except json.JSONDecodeError:
            # 不是 json 格式就直接返回字符串
            return val.decode("utf-8") if isinstance(val, bytes) else val  # 将字节串解码为字符串

    @staticmethod
    def iso_to_standard_datetimestr(datestr: str, time_zone_step: int) -> str:
        """iso(2024-04-21T04:20:00Z)格式转 标准的时间格式(2024-01-01 00:00:00)"""
        dt_str = "{} {}".format(datestr[:10], datestr[11:-1])
        dt = datetime.strptime(dt_str, standard_date_format)
        dt_step = dt + timedelta(hours=time_zone_step)
        return dt_step.strftime(standard_date_format)

    def iso_to_standard_datestr(self, datestr: str, time_zone_step: int) -> str:
        """iso(2024-04-21T04:20:00Z)格式转 标准的时间格式(2024-01-01)"""
        return self.iso_to_standard_datetimestr(datestr=datestr, time_zone_step=time_zone_step)[:10]

    @staticmethod
    def gen_qlv_login_state_key() -> str:
        return ":".join(["qlv", "login", "state"])


class AsyncReliableQueue:
    """
    循环可靠队列（适合 Cron/定时任务）
    """

    def __init__(self, redis: redis.Redis, key: str):
        self.redis = redis
        self.pending = ":".join(["queue", "pending", key])
        self.processing = ":".join(["queue", "processing", key])

        # 使用 Lua 做 pop（原子操作）
        self.pop_script = redis.register_script("""
        -- 从队尾取出
        local task = redis.call('RPOP', KEYS[1])
        if not task then
            return nil
        end
        -- 放入 processing
        redis.call('LPUSH', KEYS[2], task)
        return task
        """)

    async def add(self, task: str) -> None:
        """生产者：插入队首（FIFO 原生支持）"""
        await self.redis.lpush(self.pending, task)

    async def pop(self) -> Optional[str]:
        """消费者：FIFO 从队尾取出任务，并放入 processing（原子操作）"""
        return await self.pop_script(keys=[self.pending, self.processing], args=[])

    async def finish(self, task: str):
        """任务完成：从 processing 中删除"""
        await self.redis.lrem(self.processing, 1, task)

    async def requeue(self, task: str):
        """任务回队首：从 processing 删除 → 回 pending 队首"""
        pipe = self.redis.pipeline()
        await pipe.lrem(self.processing, 1, task)
        await pipe.lpush(self.pending, task)
        await pipe.execute()

    async def recover(self):
        """恢复崩溃中的任务：processing → pending 队首"""
        tasks = await self.redis.lrange(self.processing, 0, -1)
        if not tasks:
            return 0

        pipe = self.redis.pipeline()
        for t in tasks:
            await pipe.lrem(self.processing, 1, t)
            await pipe.lpush(self.pending, t)
        await pipe.execute()

        return len(tasks)


redis_client = AsyncRedisHelper(host='192.168.3.240', port=6379, db=0, password="Admin@123", decode_responses=True)
activity_order_queue = AsyncReliableQueue(
    redis=redis_client.redis, key=redis_client.gen_qlv_flight_activity_order_list_key()
)
order_state_queue = AsyncReliableQueue(
    redis=redis_client.redis, key=redis_client.gen_qlv_flight_order_state_list_key()
)
