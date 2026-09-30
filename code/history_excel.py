"""Incremental historical-result import into the explicitly selected workbook."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


class WorkbookError(ValueError):
    """An actionable workbook error, containing no session credentials."""


@dataclass(frozen=True)
class SyncReport:
    written: int
    path: Path
    skipped: int
    ambiguous: int
    written_issues: tuple[str, ...] = ()


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _locked(path: Path) -> None:
    if path.with_name("~$" + path.name).exists():
        raise WorkbookError("表格正在 Excel 中打开，请关闭后再同步。")


def _load(path: Path):
    if path.suffix.lower() != ".xlsx":
        raise WorkbookError("仅支持 .xlsx 工作簿，请先另存为 .xlsx。")
    _locked(path)
    try:
        return load_workbook(path, data_only=False, keep_links=True)
    except Exception as exc:
        raise WorkbookError("读取表格失败，请检查文件是否存在、格式及访问权限。") from exc


def import_source(path: Path) -> Path:
    """Copy once; a pre-existing output must be explicitly selected, never overwritten."""
    path = Path(path).resolve()
    workbook = _load(path)
    workbook.close()
    output = path.with_name(path.stem + "_已完成.xlsx")
    try:
        with output.open("xb") as target:
            try:
                with path.open("rb") as source:
                    import shutil
                    shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            except Exception:
                output.unlink(missing_ok=True)
                raise
    except FileExistsError as exc:
        raise WorkbookError("工作副本已存在，未覆盖。可取消“使用副本”后选择已有副本，或更换源文件名。") from exc
    except OSError as exc:
        raise WorkbookError("创建工作副本失败，请检查目录权限和磁盘空间。") from exc
    return output


def _issue(value) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value >= 0 else None
    if isinstance(value, float):
        return str(int(value)) if math.isfinite(value) and value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        value = value.strip()
        return value if re.fullmatch(r"[0-9]+", value) else None
    return None


def _empty(cell) -> bool:
    return not isinstance(cell, MergedCell) and cell.data_type != "f" and (
        cell.value is None or isinstance(cell.value, str) and not cell.value.strip()
    )


def _records(records: list[dict]) -> tuple[dict[str, int], set[str]]:
    parsed: dict[str, int] = {}
    conflicts: set[str] = set()
    for record in records:
        issue = _issue(record.get("issue")) if isinstance(record, dict) else None
        number = record.get("special_code") if isinstance(record, dict) else None
        if not issue or len(issue) <= 3 or isinstance(number, bool):
            raise WorkbookError("开奖结果字段格式不正确：需要完整期数和特码。")
        normalized = _issue(number)
        if normalized is None or not 1 <= int(normalized) <= 49:
            raise WorkbookError("开奖结果的特码应为 1–49 的整数。")
        if issue in parsed and parsed[issue] != int(normalized):
            conflicts.add(issue)
        parsed[issue] = int(normalized)
    return parsed, conflicts


class WorkbookSync:
    """One loaded snapshot. Pass cumulative records from the same selected result date.

    Short periods refer to the nearest 1000-issue cycle around the newest record.
    A distance of exactly 500 or repeated suffixes is ambiguous and is not written.
    Full periods never fall back to suffix matching. Only blank column B is written.
    """

    def __init__(self, path: Path, sheet_name: str | None = None):
        self.path = Path(path).resolve()
        try:
            before = _digest(self.path)
            self.workbook = _load(self.path)
            self._hash = _digest(self.path)
        except OSError as exc:
            raise WorkbookError("读取表格失败，请检查文件访问权限。") from exc
        if before != self._hash:
            self.workbook.close()
            raise WorkbookError("读取时表格发生变化，请重试。")
        name = sheet_name or ("记录" if "记录" in self.workbook.sheetnames else self.workbook.sheetnames[0])
        if name not in self.workbook.sheetnames:
            self.workbook.close()
            raise WorkbookError("指定的工作表不存在。")
        self.sheet = self.workbook[name]

    @property
    def pending_count(self) -> int:
        return len(self._rows(pending_only=True))

    def _rows(self, pending_only=False) -> dict[int, str]:
        rows = {}
        for row in self.sheet.iter_rows(min_col=1, max_col=2):
            period, output = row
            issue = _issue(period.value)
            if issue is not None and (not pending_only or _empty(output)):
                rows[period.row] = issue
        return rows

    def _targets(self, parsed: dict[str, int]) -> tuple[dict[int, str], set[int]]:
        if not parsed:
            return {}, set()
        latest = max(map(int, parsed))
        suffixes: dict[str, set[str]] = defaultdict(set)
        for issue in parsed:
            suffixes[issue[-3:]].add(issue)
        targets: dict[int, str] = {}
        ambiguous: set[int] = set()
        owners: dict[str, list[int]] = defaultdict(list)
        for row, issue in self._rows().items():
            if len(issue) > 3:
                target = issue
            else:
                suffix = issue.zfill(3)
                age = (latest - int(suffix)) % 1000
                if age == 500 or len(suffixes[suffix]) > 1:
                    ambiguous.add(row)
                    continue
                target = str(latest - age if age < 500 else latest + 1000 - age)
            targets[row] = target
            owners[target].append(row)
        for rows in owners.values():
            if len(rows) > 1:
                ambiguous.update(rows)
        return targets, ambiguous

    def needs_more(self, records: list[dict]) -> bool:
        """Fetch another page only if a pending, unambiguous period precedes this batch."""
        if not records or not self.pending_count:
            return False
        parsed, conflicts = _records(records)
        targets, ambiguous = self._targets(parsed)
        oldest = min(map(int, parsed))
        for row in self._rows(pending_only=True):
            if row in ambiguous:
                continue
            target = targets[row]
            if target not in parsed and target not in conflicts and int(target) < oldest:
                return True
        return False

    def apply(self, records: list[dict]) -> SyncReport:
        parsed, conflicts = _records(records)
        targets, ambiguous = self._targets(parsed)
        pending = self._rows(pending_only=True)
        formula_changes = self._upgrade_blank_d_formulas()
        changes = []
        for row in pending:
            target = targets.get(row)
            if row not in ambiguous and target in parsed and target not in conflicts:
                changes.append((row, parsed[target]))
        conflict_rows = {row for row, target in targets.items() if target in conflicts}
        report = SyncReport(
            len(changes), self.path, len(pending) - len(changes),
            len((ambiguous | conflict_rows) & pending.keys()),
            tuple(targets[row] for row, _number in changes),
        )
        if not changes and not formula_changes:
            return report
        previous = {row: self.sheet.cell(row, 2).value for row, _ in changes}
        for row, number in changes:
            self.sheet.cell(row, 2).value = number
        try:
            if formula_changes:
                calculation = getattr(self.workbook, "calculation", None)
                if calculation is not None:
                    calculation.fullCalcOnLoad = True
                    calculation.forceFullCalc = True
            self._save()
        except Exception:
            for row, value in previous.items():
                self.sheet.cell(row, 2).value = value
            for row, value in formula_changes.items():
                self.sheet.cell(row, 4).value = value
            raise
        return report

    def _upgrade_blank_d_formulas(self) -> dict[int, str]:
        """Migrate only the legacy generated formulas; custom templates stay untouched."""
        previous: dict[int, str] = {}
        for row, _issue_value in self._rows().items():
            cell = self.sheet.cell(row, 4)
            value = cell.value
            if not isinstance(value, str) or cell.data_type != "f":
                continue
            if row == 3 and value == '=IF(B3="","",1)':
                replacement = '=IF(B3="",1,1)'
            else:
                prefix = f'=IF(B{row}="","",'
                if not value.startswith(prefix):
                    continue
                replacement = (
                    f'=IF(B{row}="",IF(ISNUMBER(D{row - 1}),D{row - 1}+1,1),'
                    + value[len(prefix):]
                )
            previous[row] = value
            cell.value = replacement
        return previous

    def _check_unchanged(self):
        _locked(self.path)
        if _digest(self.path) != self._hash:
            raise WorkbookError("工作副本已被其他程序修改，本次未写入；请重新加载表格。")

    def _save(self):
        temporary = None
        try:
            self._check_unchanged()
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".history-", suffix=".xlsx", delete=False) as stream:
                temporary = Path(stream.name)
            self.workbook.save(temporary)
            # Windows implements os.fsync with FlushFileBuffers/_commit, which
            # requires a writable descriptor. Opening this as "rb" works on
            # POSIX but deterministically fails in the packaged Windows app.
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            self._check_unchanged()
            os.replace(temporary, self.path)
            self._hash = _digest(self.path)
        except WorkbookError:
            raise
        except OSError as exc:
            code = getattr(exc, "winerror", None) or exc.errno
            reason = exc.strerror or type(exc).__name__
            detail = f"（系统错误 {code}：{reason}）" if code else f"（{reason}）"
            raise WorkbookError(
                f"保存表格失败{detail}。请检查文件权限和磁盘空间；如果表格已打开，请先关闭。"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def close(self):
        self.workbook.close()
