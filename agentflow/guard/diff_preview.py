"""修改前 diff 预览与确认交互。

对应 MVP P0「修改前强制 diff 预览 + 确认」。
diff 生成优先用 GitPython（工作区 vs HEAD），非 git 环境退化为内容摘要；
确认支持交互式 y/n 与本会话内 yes-to-all。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from agentflow.guard.engine import FileChange

ApprovalMethod = Literal["interactive", "yes-to-all", "aborted", "skipped"]

#: diff 文本最大展示行数（超出截断）。
MAX_DIFF_LINES = 200


@dataclass(frozen=True)
class DiffPreview:
    """一组改动的 diff 预览。"""

    changes: tuple[FileChange, ...]
    diff_text: str
    summary: tuple[str, ...]  # 每个文件一行的人读摘要


@dataclass(frozen=True)
class ApprovalResult:
    """确认结果。method=skipped 表示未启用 diff 预览直接放行。"""

    approved: bool
    method: ApprovalMethod


def _truncate(text: str, limit: int = MAX_DIFF_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit]) + f"\n...（已截断，共 {len(lines)} 行）"


class DiffPreviewer:
    """生成 diff 预览并收集确认。"""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._yes_to_all = False

    def _git_diff(self, rel: str) -> str | None:
        """取该路径相对 HEAD 的 diff；非 git 环境 / 无差异返回 None。"""
        try:
            from git import Repo

            repo = Repo(self._root, search_parent_directories=True)
            return repo.git.diff("HEAD", "--", rel) or None
        except Exception:  # noqa: BLE001 - 非 git / 空仓库 / git 缺失均走退化路径
            return None

    def _diff_for(self, change: FileChange) -> tuple[str, str]:
        """返回 (diff 文本, 人读摘要)。"""
        rel = change.path.as_posix()
        target = self._root / change.path

        git_diff = self._git_diff(rel)
        if git_diff:
            return _truncate(git_diff), f"[{change.change_type}] {rel}（git diff vs HEAD）"

        if change.change_type == "create":
            if target.is_file():
                content = target.read_text(encoding="utf-8", errors="replace")
                body = "\n".join(f"+{line}" for line in content.splitlines())
                text = f"--- /dev/null\n+++ {rel}\n{body}" if body else f"+++ {rel}（空文件）"
                return _truncate(text), f"[create] {rel}（新增 {len(content.splitlines())} 行）"
            return f"+++ {rel}（新文件，尚无内容）", f"[create] {rel}（新文件）"

        if change.change_type == "delete":
            if target.is_file():
                n = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
                return f"--- {rel}（将删除，当前 {n} 行）", f"[delete] {rel}（删除 {n} 行）"
            return f"--- {rel}（文件不存在）", f"[delete] {rel}（文件不存在）"

        # modify 且拿不到 git diff：展示当前内容头部作为基线参考
        if target.is_file():
            head = "\n".join(target.read_text(encoding="utf-8", errors="replace").splitlines()[:20])
            text = f"（非 git 环境或无 HEAD 差异，当前内容前 20 行）\n{rel}\n{head}"
            return _truncate(text), f"[modify] {rel}（当前内容前 20 行）"
        return f"{rel}（文件不存在，将按新增处理）", f"[modify] {rel}（文件不存在）"

    def build_preview(self, changes: Sequence[FileChange]) -> DiffPreview:
        """为一组改动生成 diff 文本与摘要。"""
        chunks: list[str] = []
        summary: list[str] = []
        for change in changes:
            text, note = self._diff_for(change)
            chunks.append(text)
            summary.append(note)
        return DiffPreview(
            changes=tuple(changes),
            diff_text="\n\n".join(chunks),
            summary=tuple(summary),
        )

    def request_approval(self, preview: DiffPreview) -> ApprovalResult:
        """向用户展示预览并收集确认（y / n / a=本次会话全部允许）。

        非交互环境（无 tty）默认拒绝，交由上层决定如何处理。
        """
        if self._yes_to_all:
            return ApprovalResult(approved=True, method="yes-to-all")

        if not sys.stdin.isatty():
            return ApprovalResult(approved=False, method="aborted")

        print("\n=== 改动预览 ===")
        for note in preview.summary:
            print(f"  {note}")
        if preview.diff_text:
            print("\n" + preview.diff_text)
        answer = input("确认执行以上改动? [y=确认 / n=取消 / a=本次会话全部允许] ").strip().lower()
        if answer == "y":
            return ApprovalResult(approved=True, method="interactive")
        if answer == "a":
            self._yes_to_all = True
            return ApprovalResult(approved=True, method="yes-to-all")
        return ApprovalResult(approved=False, method="aborted")
