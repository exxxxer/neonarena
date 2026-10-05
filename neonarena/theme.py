"""Shared Qt Style Sheets; all screen layouts live in .ui files."""

STYLE = """
QWidget { background: #090f20; color: #dfeaff; font-family: 'Segoe UI',
 'DejaVu Sans'; font-size: 13px; }
QLabel#brandLabel { font-size: 42px; font-weight: 800; color: #57edff; }
QLabel#titleLabel { font-size: 27px; font-weight: 700; }
QLabel#subtitleLabel, QLabel#hintLabel { color: #91a6c2; }
QLabel#eyebrowLabel { color: #b38aff; font-size: 12px; font-weight: 700; }
QLabel#profileStatsLabel { color: #57edff; }
QLabel#waveLabel, QLabel#scoreLabel { font-size: 20px; font-weight: 700; }
QLabel#dashLabel { color: #57edff; }
QFrame#controlPanel { background: #101a30; border: 1px solid #263955;
 border-radius: 12px; padding: 12px; }
QFrame#controlPanel QLabel { background: transparent; border: none; padding: 2px; }
QPushButton { background: #192943; border: 1px solid #354c6d; border-radius: 7px;
 padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #294266; border-color: #57edff; }
QPushButton:disabled { color: #52657c; }
QPushButton#startButton, QPushButton#againButton, QPushButton#saveButton {
 background: #57edff; color: #091323; border: none; }
QPushButton#startButton { padding: 15px; font-size: 16px; }
QPushButton#startButton:hover, QPushButton#againButton:hover,
QPushButton#saveButton:hover { background: #acf7ff; }
QPushButton#upgradeButton0, QPushButton#upgradeButton1, QPushButton#upgradeButton2 {
 text-align: left; background: #17263f; padding: 16px 25px; font-size: 16px; }
QComboBox, QLineEdit { background: #15233b; border: 1px solid #354c6d;
 border-radius: 5px; padding: 8px; }
QComboBox QAbstractItemView { background: #15233b; selection-background-color: #354c6d; }
QTabWidget::pane { border: none; padding-top: 12px; }
QTabBar::tab { padding: 11px 26px; background: #101a30; color: #91a6c2; }
QTabBar::tab:selected { color: #57edff; border-bottom: 2px solid #57edff; }
QTextBrowser, QTableWidget { background: #101a30; border: 1px solid #263955;
 border-radius: 8px; padding: 10px; selection-background-color: #354c6d; }
QHeaderView::section { background: #192943; color: #91a6c2; padding: 9px; border: none; }
QProgressBar { border: none; border-radius: 5px; background: #23304b; min-height: 16px;
 text-align: center; }
QProgressBar::chunk { background: #57edff; border-radius: 5px; }
QSlider::groove:horizontal { height: 5px; background: #354c6d; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 7px;
 background: #57edff; }
QCheckBox { spacing: 9px; }
QStatusBar { color: #7492ad; }
"""
