"""One bounded read-only query + atomic workbook update, run outside the GUI thread."""
from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal
from bet_client import AutoBetRunner, BetPlan
from bet_rules import PLAY1, evaluate_bet_rule
from history_client import HistoryClient, HistoryError, safe_message
from history_excel import WorkbookSync
from sheet_book import NoSheetResults
from settings_store import load_settings, save_profit_snapshot, site_day


class ResultFetchWorker(QThread):
    """Read one openResultList page. The dialog asks for the next page as the user scrolls."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, site: str, auth: dict, day: str, page: int, parent=None):
        super().__init__(parent)
        self.site, self.auth, self.day, self.page = site, dict(auth), day, page
        self.cancel = Event()

    def run(self) -> None:
        try:
            if self.cancel.is_set():
                return
            rows = HistoryClient(self.site, self.auth).fetch_page(self.day, self.page)
            if self.cancel.is_set():
                return
            self.succeeded.emit({"page": self.page, "rows": rows})
        except (OSError, ValueError) as exc:
            from history_client import safe_message
            self.failed.emit(safe_message(str(exc), tuple(str(v) for v in self.auth.values())))
        except Exception:
            self.failed.emit("历史结果查询异常，请检查网页地址和登录态")
        finally:
            self.auth = {}


class HistoryWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    bet_succeeded = Signal(str)
    bet_failed = Signal(str)
    profit_checked = Signal(float, bool, str)
    profit_failed = Signal(str)

    def __init__(self, site: str, auth: dict, workbook: str, day: str,
                 parent=None, bet_plan: BetPlan | None = None,
                 bet_rule_key: str = PLAY1):
        super().__init__(parent)
        self.site, self.auth, self.workbook, self.day = site, auth, workbook, day
        self.bet_plan = bet_plan
        self.bet_rule_key = bet_rule_key
        self.cancel = Event()

    def run(self) -> None:
        sync = None
        try:
            sync = WorkbookSync(Path(self.workbook))
            client = HistoryClient(self.site, self.auth)
            rows, pages, seen_pages = [], 0, set()
            for page in range(1, 51):
                if self.cancel.is_set():
                    return
                fetched = client.fetch_page(self.day, page)
                pages = page
                if self.cancel.is_set():
                    return
                if not fetched:
                    break
                signature = tuple(row["issue"] for row in fetched)
                if signature in seen_pages:
                    raise HistoryError("接口重复返回同一页，已中止分页；未保存本轮数据")
                seen_pages.add(signature)
                rows.extend(fetched)
                self.progress.emit(f"已查询 {self.day} 第 {page} 页：{len(fetched)} 条历史结果")
                if not sync.needs_more(rows):
                    break
                if self.cancel.wait(0.2):
                    return
            else:
                raise HistoryError("已到单轮 50 页上限，请缩小日期/表格范围；本轮未保存")
            if self.cancel.is_set():
                return
            report = sync.apply(rows)
            if self.bet_plan is not None and not self.cancel.is_set():
                try:
                    latest_settings = load_settings()
                    if latest_settings.profit_halt_date == site_day():
                        self.progress.emit(
                            latest_settings.profit_halt_reason
                            or "今日已达到盈亏停止值，本期不自动投注"
                        )
                        self.succeeded.emit({
                            "rows": rows, "report": report,
                            "pages": pages, "date": self.day,
                        })
                        return
                    runner = AutoBetRunner(self.site, self.auth)
                    if (getattr(latest_settings, "profit_limit", None) is not None
                            or getattr(latest_settings, "loss_limit", None) is not None):
                        try:
                            value = runner.client.today_profit()
                            halted, reason = save_profit_snapshot(value)
                        except (OSError, ValueError) as exc:
                            self.profit_failed.emit(
                                "自动盈亏检查失败，本期停止投注：" + safe_message(
                                    str(exc), tuple(str(v) for v in self.auth.values())
                                )
                            )
                            self.succeeded.emit({
                                "rows": rows, "report": report,
                                "pages": pages, "date": self.day,
                            })
                            return
                        self.profit_checked.emit(value, halted, reason)
                        if halted:
                            self.progress.emit(reason + "，今日自动投注已停止")
                            self.succeeded.emit({
                                "rows": rows, "report": report,
                                "pages": pages, "date": self.day,
                            })
                            return
                    try:
                        current_issue = max(
                            (str(row["issue"]) for row in rows), key=int, default=None
                        )
                        decision = evaluate_bet_rule(
                            self.bet_rule_key,
                            Path(self.workbook),
                            report.written_issues,
                            current_issue,
                        )
                    except NoSheetResults:
                        # A freshly cleared daily template is expected to be
                        # empty before its first matching result is published.
                        # History sync has already run; wait for a later poll
                        # instead of treating the valid empty sheet as a fault.
                        self.progress.emit(
                            "表格暂无已补录特码，等待开奖结果后再判断自动投注"
                        )
                        self.succeeded.emit({
                            "rows": rows, "report": report,
                            "pages": pages, "date": self.day,
                        })
                        return
                    plan = BetPlan(self.bet_plan.count, self.bet_plan.points,
                                   decision.tail, decision.zodiac,
                                   self.bet_plan.start_offset,
                                   self.bet_plan.point_schedule,
                                   decision.rule_key)
                    outcome = runner.run_once(
                        plan, decision.trigger_issue, latest_result_issue=current_issue
                    )
                    if outcome is not None:
                        numbers = "、".join(number for number, _ in outcome.bets)
                        amounts = "、".join(str(amount) for _, amount in outcome.bets)
                        detail = (
                            f"{outcome.issue}期，投注了{numbers}，共{outcome.selected}个号码，"
                            f"每个号码积分各是{amounts}。"
                            if outcome.bets else
                            f"{outcome.issue}期，共投注{outcome.selected}个号码，"
                            f"每个号码{outcome.points}积分。"
                        )
                        self.bet_succeeded.emit(
                            f"自动投注成功：{detail} 玩法：特码B；规则：{decision.label}；"
                            f"排除{decision.exclusion_text}；"
                            f"本期合计{outcome.total_points}积分；"
                            f"进度 {outcome.completed}/{outcome.target_count}（{outcome.message}）"
                        )
                except (OSError, ValueError) as exc:
                    self.bet_failed.emit(
                        "自动投注失败：" + safe_message(
                            str(exc), tuple(str(v) for v in self.auth.values())
                        )
                    )
            self.succeeded.emit({"rows": rows, "report": report, "pages": pages, "date": self.day})
        except (OSError, ValueError) as exc:
            # No request/response dump: all domain errors must be secret-free.
            self.failed.emit(safe_message(str(exc), tuple(str(v) for v in self.auth.values())))
        except Exception:
            self.failed.emit("查询或工作簿处理异常，本轮已停止，请检查文件格式")
        finally:
            if sync is not None:
                sync.close()
            self.auth = {}
