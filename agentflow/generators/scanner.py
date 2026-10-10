"""项目扫描器：探测技术栈，产出 ProjectProfile。

基础版（P0）：按特征文件识别；内容级智能分析属 P1 增强。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProjectProfile:
    """扫描结果：生成 AGENTS.md / Cursor rules 的数据来源。"""

    root: Path
    project_name: str
    languages: tuple[str, ...] = ()
    package_managers: tuple[str, ...] = ()
    test_frameworks: tuple[str, ...] = ()
    build_tools: tuple[str, ...] = ()
    is_git_repo: bool = False
    key_files: tuple[str, ...] = field(default=())  # 探测到的 pyproject.toml / package.json 等


def _unique(items: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


class ProjectScanner:
    """按特征文件探测技术栈。"""

    #: 特征文件 → (语言, 包管理器, 测试框架, 构建工具)；多值用 "/" 分隔。
    SIGNATURES = {
        "pyproject.toml": ("python", "pip/poetry/uv", "pytest", "hatch/build"),
        "requirements.txt": ("python", "pip", "pytest", ""),
        "package.json": ("typescript/javascript", "npm/pnpm/yarn", "jest/vitest", ""),
        "go.mod": ("go", "go modules", "go test", ""),
        "Cargo.toml": ("rust", "cargo", "cargo test", "cargo"),
        "pom.xml": ("java", "maven", "junit", "maven"),
    }

    def scan(self, root: Path | None = None) -> ProjectProfile:
        """扫描项目根目录，返回技术栈画像。

        读取根目录特征文件（SIGNATURES）；git 检测用 .git 目录；
        project_name 取根目录名。不做内容级分析（P1 增强）。
        """
        root = Path(root) if root is not None else Path.cwd()

        languages: list[str] = []
        package_managers: list[str] = []
        test_frameworks: list[str] = []
        build_tools: list[str] = []
        key_files: list[str] = []

        for filename, (lang, pm, test, build) in self.SIGNATURES.items():
            if not (root / filename).is_file():
                continue
            key_files.append(filename)
            languages.extend(lang.split("/"))
            package_managers.extend(pm.split("/"))
            test_frameworks.extend(test.split("/"))
            build_tools.extend(build.split("/"))

        return ProjectProfile(
            root=root,
            project_name=root.name,
            languages=_unique(languages),
            package_managers=_unique(package_managers),
            test_frameworks=_unique(test_frameworks),
            build_tools=_unique(build_tools),
            is_git_repo=(root / ".git").exists(),
            key_files=tuple(key_files),
        )
