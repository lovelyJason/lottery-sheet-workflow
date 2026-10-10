"""Application stylesheet. Colors come from the mascot: sky blue, collar red, bell gold, paper."""

PAPER = "#F6F1E6"
INK = "#1C2430"
MUTED = "#5E6876"
LINE = "#E4DCCE"
BLUE = "#1677D2"
BLUE_HOVER = "#0F68BC"
BLUE_PRESS = "#0C569C"
RED = "#D23B3B"
RED_SOFT = "#F8D6D6"
GOLD_BG = "#FFF3D1"
GOLD_INK = "#8A5A00"
GREEN_BG = "#E5F6EC"
GREEN_INK = "#176B3A"
WHITE = "#FFFFFF"

APP_STYLESHEET = f"""
QMainWindow {{
    background: {PAPER};
}}
QWidget#canvas {{
    background: {PAPER};
}}
QDialog {{
    background: {PAPER};
}}
QLabel {{
    background: transparent;
    color: {INK};
    font-size: 14px;
}}
QLabel#title {{
    font-size: 22px;
    font-weight: 700;
}}
QLabel#subtitle {{
    font-size: 13px;
    color: rgba(255, 255, 255, 0.90);
}}
QLabel#heading {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel#hint {{
    color: {MUTED};
    font-size: 13px;
}}
QLabel#caption {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#value {{
    color: {INK};
    font-size: 13px;
    font-family: Menlo, monospace;
}}
QLabel#badge {{
    font-size: 12px;
    font-weight: 700;
    min-height: 18px;
    padding: 3px 10px;
    border-radius: 10px;
}}
QLabel#badge[state="ready"] {{
    background: {GREEN_BG};
    color: {GREEN_INK};
}}
QFrame#hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #146FCA, stop:0.58 {BLUE}, stop:0.84 #49A4F0, stop:1 #F0B429);
    border: none;
    border-radius: 18px;
}}
QFrame#hero QLabel#title {{
    color: {WHITE};
}}
QFrame#card {{
    background: {WHITE};
    border: 1px solid {LINE};
    border-radius: 16px;
}}
QWidget#rule {{
    background: {LINE};
}}
QPushButton {{
    background: {WHITE};
    color: {INK};
    border: 1px solid #D5CBBA;
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    min-height: 18px;
}}
QPushButton:hover {{
    background: #F3F8FD;
    border-color: {BLUE};
    color: {BLUE};
}}
QPushButton:pressed {{
    background: #E5F0FB;
}}
QPushButton:focus {{
    border: 2px solid {BLUE};
}}
QPushButton[role="primary"] {{
    background: {BLUE};
    color: {WHITE};
    border: 1px solid {BLUE};
}}
QPushButton[role="primary"]:hover {{
    background: {BLUE_HOVER};
    border-color: {BLUE_HOVER};
    color: {WHITE};
}}
QPushButton[role="primary"]:pressed {{
    background: {BLUE_PRESS};
    border-color: {BLUE_PRESS};
    color: {WHITE};
}}
QPushButton[role="primary"]:focus {{
    border: 2px solid #083E73;
}}
QPushButton[role="danger"] {{
    background: {WHITE};
    color: {RED};
    border: 1px solid {RED_SOFT};
}}
QPushButton[role="danger"]:hover {{
    background: #FFF5F5;
    color: {RED};
    border-color: {RED};
}}
QPushButton[role="danger"]:pressed {{
    background: #FDE8E8;
    color: {RED};
}}
QPushButton:disabled {{
    background: #F3F0EA;
    color: #B0A89C;
    border: 1px solid {LINE};
}}
QLineEdit, QPlainTextEdit {{
    background: {WHITE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: {BLUE};
    selection-color: {WHITE};
}}
QPlainTextEdit {{
    font-family: Menlo, monospace;
    font-size: 12px;
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {BLUE};
}}
QFrame#pointsFrame {{
    background: {WHITE};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
QScrollArea#pointsScroll,
QScrollArea#pointsScroll QWidget#qt_scrollarea_viewport,
QWidget#pointsContainer {{
    background: transparent;
    border: none;
}}
QLabel#error {{
    color: {RED};
    font-size: 13px;
}}
QTableWidget {{
    background: {WHITE};
    alternate-background-color: {WHITE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 12px;
    gridline-color: {LINE};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 6px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px;
}}
QScrollBar::handle:vertical {{
    background: #D5CBBA;
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: #B7AD9C;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QStatusBar {{
    background: {PAPER};
    color: {MUTED};
    border-top: 1px solid {LINE};
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}
QMessageBox {{
    background: {PAPER};
}}
QMessageBox QLabel {{
    color: {INK};
    font-size: 14px;
}}
QFrame#toast {{
    background: {WHITE};
    border: 1px solid #FFD1D1;
    border-radius: 10px;
}}
QFrame#toast[kind="success"] {{ border-color: #B7E7C9; }}
QFrame#toast QLabel#toastText {{
    color: {INK}; font-size: 13px; font-weight: 600;
}}
QFrame#toast QLabel#toastIcon {{
    background: {RED}; color: {WHITE}; border-radius: 10px;
    font-size: 13px; font-weight: 700;
}}
QFrame#toast[kind="success"] QLabel#toastIcon {{ background: #28A35A; }}
"""

# Scoped desktop configuration surface; preserve the surrounding application's palette.
CONFIG_BG = "#F3F7FC"
CONFIG_LINE = "#DCE5F0"
CONFIG_SOFT = "#F6F9FD"
CONFIG_BLUE_SOFT = "#EAF3FF"

DRAW_CONFIG_STYLE = f"""
QWidget#drawConfig {{ background: {CONFIG_BG}; }}
QFrame#configHero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BLUE_HOVER}, stop:1 {BLUE});
    border-radius: 14px;
}}
QFrame#configHero QLabel {{ color: {WHITE}; font-size: 12px; }}
QFrame#configHero QLabel#configTitle {{ font-size: 22px; font-weight: 700; }}
QTabWidget#configTabs::pane {{ border: none; background: {WHITE}; border-radius: 14px; }}
QTabWidget#configTabs QTabBar::tab {{
    color: {MUTED}; background: transparent; border: none;
    padding: 10px 16px; margin-right: 6px; margin-bottom: 6px;
    font-size: 13px; font-weight: 600;
}}
QTabWidget#configTabs QTabBar::tab:selected {{
    color: {BLUE}; background: {CONFIG_BLUE_SOFT}; border-radius: 8px;
}}
QTabWidget#configTabs QTabBar::tab:hover {{ color: {BLUE}; }}
QFrame#card {{ border: 1px solid {CONFIG_LINE}; background: {WHITE}; border-radius: 14px; }}
QFrame#fileSurface {{ background: {CONFIG_SOFT}; border: 1px solid {CONFIG_LINE}; border-radius: 10px; }}
QFrame#modeSurface {{ background: {CONFIG_SOFT}; border: 1px solid {CONFIG_LINE}; border-radius: 10px; }}
QFrame#logicSurface {{ background: {WHITE}; border: 1px solid {CONFIG_LINE}; border-radius: 8px; }}
QLabel#sectionLabel {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#workbookName {{ font-size: 15px; font-weight: 600; color: {INK}; }}
QLabel#syncBadge {{
    background: {CONFIG_SOFT}; color: {MUTED}; font-size: 11px;
    padding: 4px 9px; border-radius: 10px;
}}
QLabel#syncBadge[active="true"] {{ background: {CONFIG_BLUE_SOFT}; color: {BLUE}; }}
QLabel#mappingHint {{ color: {MUTED}; font-size: 12px; }}
QFrame#syncStatus {{ background: {CONFIG_BLUE_SOFT}; border: none; border-radius: 8px; }}
QFrame#syncStatus QLabel {{ color: #31567D; font-size: 13px; }}
QPushButton {{ border-color: {CONFIG_LINE}; padding: 7px 12px; border-radius: 8px; }}
QPushButton[role="primary"] {{ background: {BLUE}; color: {WHITE}; border-color: {BLUE}; }}
QPushButton[role="primary"]:hover {{ background: {BLUE_HOVER}; color: {WHITE}; }}
QPushButton[role="primary"]:pressed {{ background: {BLUE_PRESS}; color: {WHITE}; }}
QPushButton:disabled, QPushButton[role="primary"]:disabled {{
    background: #F2F5F9; color: #A1ACBA; border-color: {CONFIG_LINE};
}}
QCheckBox#copyToggle {{
    spacing: 8px; padding: 0px; margin: 0px;
}}
QCheckBox#copyToggle::indicator {{
    subcontrol-origin: content;
    subcontrol-position: left center;
}}
QCheckBox {{ color: {INK}; font-size: 13px; spacing: 8px; background: transparent; }}
QRadioButton#modeChoice {{
    color: {INK}; font-size: 13px; spacing: 8px; background: transparent;
    padding: 2px 0;
}}
QRadioButton#modeChoice::indicator {{ width: 18px; height: 18px; }}
QRadioButton#modeChoice:disabled {{ color: #9BA8B8; }}
QToolButton#optionHelp {{
    background: {CONFIG_BLUE_SOFT}; color: {BLUE}; border: 1px solid #A9D2F5;
    border-radius: 11px; font-weight: 700; padding: 0;
}}
QToolButton#optionHelp:hover {{ background: {BLUE}; color: {WHITE}; border-color: {BLUE}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QCheckBox:disabled {{ color: #9BA8B8; }}
QDateEdit {{
    background: {WHITE}; color: {INK}; border: 1px solid {CONFIG_LINE};
    border-radius: 8px; padding: 7px 10px; font-size: 13px;
    selection-background-color: {BLUE}; selection-color: {WHITE};
}}
QDateEdit:focus {{ border-color: {BLUE}; }}
QDateEdit:disabled {{ background: #F2F5F9; color: #8795A6; }}
QDateEdit::drop-down {{ border: none; width: 26px; }}
QCalendarWidget QWidget {{ background: {WHITE}; color: {INK}; }}
QCalendarWidget QToolButton {{ background: {CONFIG_BLUE_SOFT}; color: {BLUE}; padding: 6px; }}
QCalendarWidget QAbstractItemView {{ selection-background-color: {BLUE}; selection-color: {WHITE}; }}
"""


from pathlib import Path as _Path
_CONFIG_ASSETS = (_Path(__file__).resolve().parent / "assets").as_posix()
DRAW_CONFIG_STYLE += f"""
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid #BCCADA;
    border-radius: 4px; background: {WHITE};
}}
QCheckBox::indicator:checked {{
    border-color: {BLUE}; background: {BLUE};
    image: url("{_CONFIG_ASSETS}/config-check.svg");
}}
QCheckBox::indicator:disabled {{ border-color: {CONFIG_LINE}; background: #E5EBF2; }}
QCheckBox#copyToggle::indicator {{
    subcontrol-origin: content;
    subcontrol-position: left center;
}}
QRadioButton#modeChoice::indicator:unchecked {{
    image: url("{_CONFIG_ASSETS}/config-radio.svg");
}}
QRadioButton#modeChoice::indicator:unchecked:hover,
QRadioButton#modeChoice::indicator:unchecked:focus {{
    image: url("{_CONFIG_ASSETS}/config-radio-hover.svg");
}}
QRadioButton#modeChoice::indicator:checked {{
    image: url("{_CONFIG_ASSETS}/config-radio-checked.svg");
}}
QRadioButton#modeChoice::indicator:checked:hover,
QRadioButton#modeChoice::indicator:checked:focus {{
    image: url("{_CONFIG_ASSETS}/config-radio-checked-hover.svg");
}}
QRadioButton#modeChoice::indicator:unchecked:disabled {{
    image: url("{_CONFIG_ASSETS}/config-radio-disabled.svg");
}}
QRadioButton#modeChoice::indicator:checked:disabled {{
    image: url("{_CONFIG_ASSETS}/config-radio-checked-disabled.svg");
}}
QDateEdit::down-arrow {{ image: url("{_CONFIG_ASSETS}/config-down.svg"); width: 12px; height: 8px; }}
"""
