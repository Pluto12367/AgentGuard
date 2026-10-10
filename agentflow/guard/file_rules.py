"""文件规则集：白名单 / 黑名单 / 保护文件的模式匹配。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Literal

from agentflow.models.config import GuardrailConfig

FileVerdict = Literal["allowed", "denied", "protected"]

#: 新增依赖时需要拦截确认的依赖清单文件（glob 模式，相对项目根）。
DEPENDENCY_MANIFEST_PATTERNS: tuple[str, ...] = (
    "pyproject.toml",
    "requirements*.txt",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
    "package.json",
    "pom.xml",
    "build.gradle*",
    "go.mod",
    "Cargo.toml",
)


@lru_cache(maxsize=1024)
def _compile(pattern: str) -> re.Pattern[str]:
    """把 gitignore 风格 glob 编译为正则。

    语义：``**`` 跨目录（可匹配零层）；``*`` / ``?`` 不跨 ``/``；
    不含 ``/`` 的模式匹配任意层级的文件名（如 ``*.pem`` 命中深层目录）。
    """
    segments = pattern.strip().replace("\\", "/").split("/")
    parts: list[str] = []
    if "/" not in pattern:
        parts.append("(?:[^/]+/)*")  # 无斜杠：任意深度

    for i, seg in enumerate(segments):
        is_last = i == len(segments) - 1
        if seg == "**":
            parts.append("(?:[^/]+(?:/[^/]+)*)?" if is_last else "(?:[^/]+/)*")
            continue
        seg_rx = "".join(
            "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in seg
        )
        parts.append(seg_rx if is_last else seg_rx + "/")

    return re.compile("".join(parts) + "$")


def glob_match(pattern: str, rel_path: str) -> bool:
    """判断相对路径（posix 风格）是否命中 glob 模式。"""
    rel = rel_path.replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return _compile(pattern).match(rel) is not None


class FileRuleSet:
    """对相对路径做三态裁决：allowed / denied / protected。"""

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def matches_any(self, rel_path: Path | str, patterns: list[str] | tuple[str, ...]) -> bool:
        rel = rel_path.as_posix() if isinstance(rel_path, Path) else str(rel_path)
        return any(glob_match(p, rel) for p in patterns)

    def classify(self, rel_path: Path | str) -> FileVerdict:
        """裁决单个文件路径。

        优先级：deny_paths → protected_files → 白名单模式（allow_paths
        非空时未命中即拒绝）。均不命中 → allowed。
        """
        if self.matches_any(rel_path, self._config.deny_paths):
            return "denied"
        if self.matches_any(rel_path, self._config.protected_files):
            return "protected"
        if self._config.allow_paths and not self.matches_any(rel_path, self._config.allow_paths):
            return "denied"
        return "allowed"

    def is_dependency_manifest(self, rel_path: Path | str) -> bool:
        """判断路径是否为依赖清单文件（配合 forbid_new_dependencies）。"""
        return self.matches_any(rel_path, DEPENDENCY_MANIFEST_PATTERNS)
