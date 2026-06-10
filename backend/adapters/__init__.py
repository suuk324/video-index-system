"""适配器基类 + 注册表"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseAdapter(ABC):
    """网站适配器抽象基类。"""
    name: str = "base"

    @abstractmethod
    def extract_items(self, html, base_url, selectors):
        """从 HTML 中提取视频条目列表。"""
        ...

    def extract_play_url(self, html, base_url):
        """从详情页提取播放链接，返回 (play_url, play_type)。"""
        return "", "unknown"


class AdapterRegistry:
    _adapters = {}

    @classmethod
    def register(cls, adapter_cls):
        cls._adapters[adapter_cls.name] = adapter_cls

    @classmethod
    def get(cls, name):
        adapter_cls = cls._adapters.get(name)
        if adapter_cls:
            return adapter_cls()
        return None

    @classmethod
    def list_adapters(cls):
        return list(cls._adapters.keys())

# 导入适配器以触发注册
from . import generic
