"""Manual, asynchronous fetch of the site's authoritative daily profit/loss value."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from bet_client import BetClient
from history_client import safe_message


class ProfitWorker(QThread):
    succeeded = Signal(float)
    failed = Signal(str)

    def __init__(self, site: str, auth: dict, parent=None, session=None):
        super().__init__(parent)
        self.site = site
        self.auth = dict(auth)
        self.session = session

    def run(self) -> None:
        try:
            if self.session is not None:
                self.auth = self.session.ensure_valid(
                    self.site, self.auth, "盈亏查询"
                )
            value = BetClient(
                self.site, self.auth, session=self.session, stage="盈亏查询"
            ).today_profit()
            self.succeeded.emit(value)
        except (OSError, ValueError) as exc:
            self.failed.emit(safe_message(
                str(exc), tuple(str(value) for value in self.auth.values())
            ))
        except Exception:
            self.failed.emit("今日盈亏查询异常，请检查网络、网站地址和登录态")
        finally:
            self.auth = {}
