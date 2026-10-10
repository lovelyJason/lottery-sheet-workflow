"""History-only polling controls; owns worker lifetime and delivers logs on GUI thread."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTimer, QUrl, Signal, Qt, QSignalBlocker
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QRadioButton, QSizePolicy, QToolButton, QVBoxLayout,
)

import app_log
from auth_storage import load
from bet_client import BetPlan
from bet_rules import rule_key
from history_client import results_url
from history_config import load_config, save_config
from history_excel import WorkbookSync
from workbook_selection import select_workbook
from history_worker import HistoryWorker
from play_options import (
    PLAY2_LOGIC_OPTIONS, PLAY_OPTIONS, PlayOption, template_kind,
)
from settings_store import load_settings, save_play_selection, site_day
from ui_common import hug
class HistoryPanel(QFrame):
    results_changed = Signal(object)
    workbook_changed = Signal()
    idle = Signal()
    state_changed = Signal(bool)
    alert_requested = Signal(str, str)
    profit_checked = Signal(float, bool, str)

    def __init__(self, parent=None, session_manager=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.worker = None
        self.session_manager = session_manager
        self.running = False
        self.last_rows = []
        self.config = load_config()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._launch)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 12)
        root.setSpacing(8)
        settings = load_settings()
        self._play_mode = settings.play_mode
        self._play2_logic = settings.play2_logic
        self._restoring_selection = False
        mode_card = QFrame()
        mode_card.setObjectName("modeSurface")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(14, 12, 14, 12)
        mode_layout.setSpacing(8)
        caption = QLabel("00  任务玩法")
        caption.setObjectName("sectionLabel")
        mode_layout.addWidget(caption)
        self.play_group, self.play_buttons, self.play_help = self._choice_row(
            mode_layout, PLAY_OPTIONS, self._play_mode, self._play_changed
        )
        self.logic_panel = QFrame()
        self.logic_panel.setObjectName("logicSurface")
        logic_layout = QVBoxLayout(self.logic_panel)
        logic_layout.setContentsMargins(12, 8, 12, 8)
        logic_layout.setSpacing(6)
        logic_caption = QLabel("玩法二投注逻辑")
        logic_caption.setObjectName("sectionLabel")
        logic_layout.addWidget(logic_caption)
        self.logic_group, self.logic_buttons, self.logic_help = self._choice_row(
            logic_layout, PLAY2_LOGIC_OPTIONS, self._play2_logic, self._logic_changed
        )
        mode_layout.addWidget(self.logic_panel)
        root.addWidget(mode_card)
        self.file_card = QFrame()
        self.file_card.setObjectName("fileSurface")
        self.file_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        file_layout = QVBoxLayout(self.file_card)
        file_layout.setContentsMargins(14, 14, 14, 24)
        file_layout.setSpacing(8)
        caption = QLabel("01  工作簿")
        caption.setObjectName("sectionLabel")
        file_layout.addWidget(caption)
        self.path_label = QLabel()
        self.path_label.setObjectName("workbookName")
        self.path_label.setTextFormat(Qt.PlainText)
        self.path_label.setWordWrap(True)
        file_layout.addWidget(self.path_label)
        self.file_hint = QLabel()
        self.file_hint.setObjectName("hint")
        self.file_hint.setWordWrap(True)
        file_layout.addWidget(self.file_hint)
        files = QHBoxLayout()
        files.setSpacing(10)
        files.setAlignment(Qt.AlignVCenter)
        self.choose = hug(QPushButton("选择 Excel"))
        self.choose.setToolTip("选择用于历史补录的 Excel，写入方式由右侧复选框决定")
        self.choose.clicked.connect(self._choose)
        self.use_copy = QCheckBox("使用副本（保留源 Excel）")
        self.use_copy.setObjectName("copyToggle")
        self.use_copy.setChecked(self.config.get("use_copy", True))
        self.use_copy.setToolTip(
            "勾选：在同目录创建副本；取消：直接修改选中的 Excel。"
            "玩法一仅补 B 列，玩法二仅补 B:H 的开奖空白。"
        )
        self.use_copy.toggled.connect(self._mode_changed)
        files.addWidget(self.choose, alignment=Qt.AlignVCenter)
        files.addWidget(self.use_copy, alignment=Qt.AlignVCenter)
        files.addStretch(1)
        file_layout.addLayout(files)
        root.addWidget(self.file_card)
        caption = QLabel("02  查询日期")
        caption.setObjectName("sectionLabel")
        root.addWidget(caption)
        dates = QHBoxLayout()
        dates.setSpacing(12)
        self.today = QCheckBox("跟随当天")
        self.today.setToolTip("使用本机日期；取消勾选后可补录指定日期")
        self.today.setChecked(not self.config.get("date"))
        self.day = QDateEdit(calendarPopup=True)
        self.day.setDisplayFormat("yyyy-MM-dd")
        self.day.setFixedWidth(164)
        initial = QDate.fromString(self.config.get("date", ""), "yyyy-MM-dd")
        self.day.setDate(initial if initial.isValid() else QDate.fromString(
            datetime.now().date().isoformat(), "yyyy-MM-dd"))
        self.day.setEnabled(not self.today.isChecked())
        self.today.toggled.connect(lambda v: self.day.setEnabled(not v and not self.busy and not self.running))
        dates.addWidget(self.today)
        dates.addWidget(self.day)
        dates.addStretch(1)
        self.interval_label = QLabel()
        self.interval_label.setObjectName("hint")
        dates.addWidget(self.interval_label)
        root.addLayout(dates)
        self.mapping_rule = QLabel()
        self.mapping_rule.setObjectName("mappingHint")
        root.addWidget(self.mapping_rule)
        note_box = QFrame()
        note_box.setObjectName("syncStatus")
        note_layout = QVBoxLayout(note_box)
        note_layout.setContentsMargins(12, 10, 12, 10)
        self.note = QLabel("先选择 Excel，点击“开始”立即补录并持续轮询。")
        self.note.setTextFormat(Qt.PlainText)
        self.note.setWordWrap(True)
        note_layout.addWidget(self.note)
        root.addWidget(note_box)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.start = hug(QPushButton("开始"), "primary")
        self.start.setToolTip("立即补录一次，随后按运行配置中的间隔自动轮询")
        self.start.clicked.connect(self._start)
        self.stop = hug(QPushButton("停止"))
        self.stop.clicked.connect(self.stop_polling)
        self.open_page = hug(QPushButton("打开开奖结果页"))
        self.open_page.clicked.connect(self._open_page)
        for button in (self.start, self.stop):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.open_page)
        root.addLayout(actions)
        scope = QLabel("支持完整期号 / 后三位；跨周期请使用完整期号。")
        scope.setObjectName("hint")
        root.addWidget(scope)
        root.addStretch(1)
        self._sync_play_visibility()
        self._controls()

    @property
    def busy(self) -> bool:
        return self.worker is not None

    def _choice_row(self, parent: QVBoxLayout, options: tuple[PlayOption, ...],
                    selected: str, callback):
        row = QHBoxLayout()
        row.setSpacing(7)
        group = QButtonGroup(self)
        buttons, helps = {}, {}
        for option in options:
            radio = QRadioButton(option.label)
            radio.setObjectName("modeChoice")
            radio.setCursor(Qt.PointingHandCursor)
            group.addButton(radio)
            buttons[option.key] = radio
            help_button = QToolButton()
            help_button.setText("?")
            help_button.setObjectName("optionHelp")
            help_button.setToolTip(option.help_text)
            help_button.setAccessibleName(f"{option.label}规则说明")
            help_button.setFixedSize(22, 22)
            help_button.setCursor(Qt.WhatsThisCursor)
            helps[option.key] = help_button
            row.addWidget(radio)
            row.addWidget(help_button)
            row.addSpacing(12)
        row.addStretch(1)
        parent.addLayout(row)
        buttons[selected].setChecked(True)
        for key, button in buttons.items():
            button.toggled.connect(
                lambda checked, value=key: checked and callback(value)
            )
        return group, buttons, helps

    def _set_choice(self, buttons: dict[str, QRadioButton], key: str) -> None:
        self._restoring_selection = True
        try:
            buttons[key].setChecked(True)
        finally:
            self._restoring_selection = False

    def _play_changed(self, value: str) -> None:
        if self._restoring_selection:
            return
        previous = self._play_mode
        if self.busy or self.running:
            self._set_choice(self.play_buttons, previous)
            return
        try:
            save_play_selection(value, self._play2_logic)
        except (OSError, ValueError) as exc:
            self._set_choice(self.play_buttons, previous)
            self.note.setText("玩法未变更：" + str(exc))
            app_log.error(str(exc))
            return
        self._play_mode = value
        self._sync_play_visibility()
        self._show_play_selection()
        self.workbook_changed.emit()

    def _logic_changed(self, value: str) -> None:
        if self._restoring_selection:
            return
        previous = self._play2_logic
        if self.busy or self.running:
            self._set_choice(self.logic_buttons, previous)
            return
        try:
            save_play_selection(self._play_mode, value)
        except (OSError, ValueError) as exc:
            self._set_choice(self.logic_buttons, previous)
            self.note.setText("玩法二逻辑未变更：" + str(exc))
            app_log.error(str(exc))
            return
        self._play2_logic = value
        self._show_play_selection()
        self.workbook_changed.emit()

    def _show_play_selection(self) -> None:
        play = next(item.label for item in PLAY_OPTIONS if item.key == self._play_mode)
        suffix = ""
        if self._play_mode == "play2":
            logic = next(
                item.label for item in PLAY2_LOGIC_OPTIONS
                if item.key == self._play2_logic
            )
            suffix = f" / {logic}"
        self.note.setText(f"已选择{play}{suffix}；点击“开始”后锁定本次任务配置。")
        app_log.info(f"任务玩法已切换为：{play}{suffix}")

    def _sync_play_visibility(self) -> None:
        is_play2 = self._play_mode == "play2"
        self.logic_panel.setVisible(is_play2)
        self.mapping_rule.setText(
            "A 列匹配期号  →  B 至 G 列依次补平1至平6，H 列补特码（合计 B:H）"
            if is_play2 else "A 列匹配期号  →  B 列仅补特码空白"
        )

    def _controls(self) -> None:
        editable = not (self.busy or self.running)
        for button in (self.start, self.choose, self.use_copy, self.today):
            button.setEnabled(editable)
        for button in (*self.play_buttons.values(), *self.logic_buttons.values()):
            button.setEnabled(editable)
        self.day.setEnabled(editable and not self.today.isChecked())
        self.stop.setEnabled(self.busy or self.running)
        self.state_changed.emit(not editable)
        path = self.config.get("workbook", "")
        name = Path(path).name if path else "尚未选择工作簿"
        self.path_label.setText(name)
        self.path_label.setToolTip(path)
        columns = "B 至 H 列开奖空白" if self._play_mode == "play2" else "B 列空白"
        self.file_hint.setText(
            f"副本模式：补录到同目录的 _已完成.xlsx，源 Excel 不变；仅填写{columns}。"
            if self.use_copy.isChecked() else
            f"直接修改：补录到所选源 Excel，仅填写{columns}。"
        )
        interval = load_settings().poll_interval
        self.interval_label.setText(f"间隔 {interval} 秒" if interval else "间隔：请到运行配置设置")

    def _select(self) -> str:
        path, _ = QFileDialog.getOpenFileName(self, "选择开奖记录表", str(Path.home()), "Excel (*.xlsx)")
        return path

    def _choose(self) -> None:
        if self.busy or self.running:
            return
        path = self._select()
        if not path:
            return
        try:
            self._bind(Path(path))
        except (OSError, ValueError) as exc:
            self._error(str(exc))

    def _mode_changed(self, checked: bool) -> None:
        previous = self.config.get("use_copy", True)
        try:
            if self.busy or self.running:
                raise ValueError("请先停止补录，再更改写入方式")
            source = self.config.get("source") or self.config.get("workbook")
            if source:
                self._bind(Path(source))
            else:
                self.config["use_copy"] = checked
                try:
                    self._save()
                except (OSError, ValueError):
                    self.config["use_copy"] = previous
                    raise
                self._controls()
        except (OSError, ValueError) as exc:
            with QSignalBlocker(self.use_copy):
                self.use_copy.setChecked(previous)
            self._controls()
            self.note.setText("写入方式未变更：" + str(exc))
            app_log.error(str(exc))

    def _bind(self, source: Path) -> None:
        if self.busy or self.running:
            raise ValueError("请先停止补录，再选择 Excel")
        source = source.resolve()
        checked = self.use_copy.isChecked()
        self._validate_workbook(source, self._play_mode)
        path = select_workbook(source, checked, self.config)
        sync = WorkbookSync(path)
        try:
            self._validate_template(sync.template_kind, self._play_mode)
            pending = sync.pending_count
        finally:
            sync.close()
        previous = self.config
        copy_path = str(path) if checked else (
            previous.get("copy_workbook", "") if previous.get("source") == str(source) else "")
        self.config = {**previous, "source": str(source), "workbook": str(path),
                       "use_copy": checked, "copy_workbook": copy_path}
        try:
            self._save()
        except (OSError, ValueError):
            self.config = previous
            raise
        self._controls()
        mode = "工作副本" if checked else "源 Excel（直接修改）"
        self.note.setText(f"已绑定{mode}，有 {pending} 期开奖数据待补录。")
        app_log.info(f"已绑定{mode}：{path.name}，待补录 {pending} 期")
        self.workbook_changed.emit()

    @staticmethod
    def _validate_template(actual: str, play_mode: str) -> None:
        expected = template_kind(play_mode)
        if actual == expected:
            return
        selected = "玩法二" if play_mode == "play2" else "玩法一"
        actual_name = "玩法二" if actual == "play_two" else "玩法一"
        raise ValueError(
            f"当前选择的是{selected}，但 Excel 是{actual_name}模板；"
            f"请重新选择对应模板。"
        )

    def _validate_workbook(self, path: Path, play_mode: str) -> None:
        sync = WorkbookSync(path)
        try:
            self._validate_template(sync.template_kind, play_mode)
        finally:
            sync.close()

    def _save(self) -> None:
        save_config(
            self.config.get("workbook", ""),
            "" if self.today.isChecked() else self.day.date().toString("yyyy-MM-dd"),
            source=self.config.get("source", ""),
            use_copy=self.config.get("use_copy", True),
            copy_workbook=self.config.get("copy_workbook", ""),
        )

    def _error(self, text: str) -> None:
        self.running = False
        self.timer.stop()
        self.note.setText("已停止：" + text)
        app_log.error(text)
        self.alert_requested.emit("运行异常", text)
        self._controls()

    def _start(self) -> None:
        if self.busy or self.running:
            return
        self.running = True
        self._launch()

    def _launch(self) -> None:
        if self.busy:
            return
        settings, auth = load_settings(), load()
        try:
            selected_rule = rule_key(settings.play_mode, settings.play2_logic)
            results_url(settings.url)
            if not auth and not (
                    self.session_manager and self.session_manager.can_auto_relogin()):
                raise ValueError("请先在“登录管理”导入单账号登录态")
            if self.running and not (settings.poll_interval and settings.poll_interval <= 2_147_483):
                raise ValueError("请在运行配置中设置 1–2147483 秒的轮询间隔")
            path = self.config.get("workbook", "")
            if not path or not Path(path).is_file():
                raise ValueError("请先选择 Excel")
            self._validate_workbook(Path(path), settings.play_mode)
            bet_plan = None
            if settings.auto_bet and settings.profit_halt_date != site_day():
                if (settings.bet_count is None
                        or len(settings.bet_points_schedule) != settings.bet_count):
                    raise ValueError("自动投注已开启，请先保存每一期的投注积分")
                bet_plan = BetPlan(settings.bet_count, settings.bet_points,
                                   None, None,
                                   settings.bet_start_offset,
                                   settings.bet_points_schedule)
            elif settings.auto_bet:
                # The stop is latched for the China-calendar day. The separate
                # profit timer keeps the home value current without repeating
                # the same warning and alarm on every history poll.
                pass
            self._save()
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        day = datetime.now().date().isoformat() if self.today.isChecked() else self.day.date().toString("yyyy-MM-dd")
        self.worker = HistoryWorker(
            settings.url, auth or {}, path, day, self, bet_plan, selected_rule,
            session=self.session_manager,
        )
        self.worker.progress.connect(self._progress)
        self.worker.bet_succeeded.connect(app_log.info)
        self.worker.bet_failed.connect(self._bet_failed)
        self.worker.profit_checked.connect(self.profit_checked.emit)
        self.worker.profit_failed.connect(self._profit_failed)
        self.worker.succeeded.connect(self._success)
        self.worker.failed.connect(self._error)
        self.worker.finished.connect(self._finished)
        self._controls()
        self.note.setText(f"正在查询 {day}，只补录空白数据…")
        self.worker.start()

    def _progress(self, text: str) -> None:
        app_log.info(text)

    def _bet_failed(self, text: str) -> None:
        app_log.error(text)
        self.alert_requested.emit("投注失败", text)

    def _profit_failed(self, text: str) -> None:
        app_log.error(text)
        self.alert_requested.emit("盈亏查询失败", text)

    def _success(self, result: dict) -> None:
        self.last_rows = result["rows"]
        report = result["report"]
        message = (f"{result['date']}：查询 {result['pages']} 页，补录 {report.written} 期；"
                   f"歧义跳过 {report.ambiguous} 项。")
        self.note.setText(message)
        app_log.info(message)
        self.results_changed.emit(self.last_rows)
        self.workbook_changed.emit()

    def _finished(self) -> None:
        worker, self.worker = self.worker, None
        worker.deleteLater()
        if self.running:
            interval = load_settings().poll_interval
            if interval and interval <= 2_147_483:
                self.timer.start(interval * 1000)
            else:
                self._error("轮询间隔无效，请修改运行配置后重新开始")
        self._controls()
        self.idle.emit()

    def stop_polling(self) -> None:
        self.running = False
        self.timer.stop()
        if self.worker:
            self.worker.cancel.set()
        self.note.setText("正在停止，等待当前请求结束…" if self.busy else "轮询已停止")
        app_log.info("停止历史轮询；不再启动下一轮查询")
        self._controls()

    def _open_page(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl(results_url(load_settings().url)))
        except ValueError as exc:
            QMessageBox.warning(self, "地址未配置", str(exc))
