"""阶段产物定义与校验。

对应 MVP P0：每个阶段必须产出指定产物（文档/代码/测试结果），
否则状态机拦截进入下一阶段。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from agentflow.core.state_machine import ArtifactSpec, Phase
from agentflow.guard.file_rules import glob_match

#: 产物匹配时忽略的目录（虚拟环境、依赖、构建产物不算「代码改动」）。
#: 注意 .agentflow 不在其中：它存放的 test-report.json 是 test 阶段的合法产物。
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".venv", "venv", "node_modules", "__pycache__", ".git", "dist", "build"}
)

#: 默认产物规格：与 CANONICAL_PHASES 对应，供状态机与 `agentflow check/advance` 使用。
DEFAULT_ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        Phase.ANALYZE,
        "分析记录（docs/ 下的 Markdown 文档）",
        ("docs/*.md", "docs/**/*.md"),
    ),
    ArtifactSpec(
        Phase.DESIGN,
        "设计文档（docs/design*.md 或 docs/design/ 目录）",
        ("docs/design*.md", "docs/design/**/*.md"),
    ),
    ArtifactSpec(
        Phase.IMPLEMENT,
        "代码改动（存在任一源码文件）",
        (
            "**/*.py",
            "**/*.js",
            "**/*.jsx",
            "**/*.ts",
            "**/*.tsx",
            "**/*.go",
            "**/*.rs",
            "**/*.java",
        ),
    ),
    ArtifactSpec(
        Phase.TEST,
        "测试报告证据（.agentflow/test-report.json，由 agentflow test 写入）",
        (".agentflow/test-report.json",),
    ),
    ArtifactSpec(
        Phase.REVIEW,
        "评审记录（docs/review*.md，可选）",
        ("docs/review*.md",),
        required=False,
    ),
)


@dataclass(frozen=True)
class ArtifactCheckResult:
    """一个阶段的产物检查结果。

    matched：产物规格描述 → 命中的文件（相对项目根）。
    missing：缺失的必需产物描述（required 且未命中的）。
    """

    phase: Phase
    satisfied: bool
    matched: dict[str, tuple[Path, ...]]
    missing: tuple[str, ...]


def _iter_rel_files(root: Path) -> Iterator[Path]:
    """遍历 root 下全部文件（相对路径），跳过 EXCLUDED_DIRS。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        base = Path(dirpath)
        for name in filenames:
            yield (base / name).relative_to(root)


class ArtifactValidator:
    """按 ArtifactSpec 的 glob 模式在项目根下查找产物文件。"""

    def __init__(self, root: Path, specs: Sequence[ArtifactSpec]) -> None:
        self._root = Path(root)
        self._specs: tuple[ArtifactSpec, ...] = tuple(specs)

    @property
    def root(self) -> Path:
        return self._root

    def specs_for(self, phase: Phase) -> tuple[ArtifactSpec, ...]:
        """返回指定阶段的全部产物规格。"""
        return tuple(spec for spec in self._specs if spec.phase is phase)

    def check(self, phase: Phase) -> ArtifactCheckResult:
        """检查指定阶段的全部产物是否齐备。

        遍历项目根下的文件（跳过 EXCLUDED_DIRS），用 gitignore 风格
        glob（** 跨目录、* 单段）匹配各规格的 path_patterns；required
        规格无任何命中即计入 missing；missing 非空则 satisfied 为 False。
        """
        matched: dict[str, tuple[Path, ...]] = {}
        missing: list[str] = []

        for spec in self.specs_for(phase):
            hits: set[Path] = {
                rel
                for rel in _iter_rel_files(self._root)
                if any(glob_match(pattern, rel.as_posix()) for pattern in spec.path_patterns)
            }
            ordered = tuple(sorted(hits, key=lambda p: p.as_posix()))
            matched[spec.description] = ordered
            if spec.required and not ordered:
                missing.append(spec.description)

        return ArtifactCheckResult(
            phase=phase,
            satisfied=not missing,
            matched=matched,
            missing=tuple(missing),
        )

    def describe(self, phase: Phase) -> tuple[str, ...]:
        """返回指定阶段各产物要求的可读描述（用于提示与报告）。"""
        return tuple(spec.description for spec in self._specs if spec.phase is phase)
