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


class AsyncRedisHelper:
    def __init__(self, **kwargs):
        self._r = redis.Redis(**kwargs)

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

    async def delete(self, key: str):
        await self._r.delete(key)

    async def close(self):
        await self._r.close()
        await self._r.connection_pool.disconnect()


redis_client = AsyncRedisHelper(host='192.168.3.240', port=6379, db=0, password="Admin@123", decode_responses=True)
