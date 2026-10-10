"""Cursor / VS Code 插件桥（P2 占位）。

设计：本地 HTTP 服务（默认 127.0.0.1:7787），插件通过它与 Python CLI 通信，
提供侧边栏阶段状态、一键确认、规则编辑等能力。零服务器、纯本地。
"""

from __future__ import annotations


class PluginBridge:
    """本地 HTTP 桥的启停接口（P2 实现）。"""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 7787

    def start(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        """启动本地 HTTP 服务，暴露状态查询 / 确认 / 规则编辑端点。"""
        raise NotImplementedError("TODO(P2): 本地 HTTP 服务")

    def stop(self) -> None:
        """停止服务。"""
        raise NotImplementedError("TODO(P2): 服务停止")
