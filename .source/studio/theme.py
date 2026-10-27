STYLE = """
QWidget { background: #242628; color: #eeeae5; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow#studioWindow, QWidget#shell { background: transparent; border: none; }
QDialog { border: 1px solid #454646; }
QLabel { background: transparent; }
QLabel#eyebrow, QLabel#section { color: #d4aa7e; font-size: 11px; letter-spacing: 1px; }
QLabel#heading { font-family: 'Bahnschrift'; font-size: 25px; font-weight: 600; }
QLabel#muted { color: #b2ada6; font-size: 12px; }
QWidget#titlebar, QWidget#footer { background: #202223; }
QWidget#titlebar { border-bottom: 1px solid #454646; border-top-left-radius: 12px; border-top-right-radius: 12px; }
QWidget#footer { border-top: 1px solid #454646; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
QMainWindow[maximized="true"] QWidget#titlebar, QMainWindow[maximized="true"] QWidget#footer { border-radius: 0; }
QLabel#brand { color: #eeeae5; font-weight: 600; }
QLabel#symbol { color: #d4aa7e; font-family: 'Consolas'; font-size: 18px; }
QPushButton { background: #2d2f31; border: 1px solid #454646; border-radius: 6px; padding: 9px 16px; min-height: 19px; }
QPushButton:hover { background: #3b3d3e; border-color: #8c7d6c; }
QPushButton:pressed { background: #413a32; }
QPushButton:disabled { color: #777976; border-color: #383a3a; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border: 1px solid #d4aa7e; }
QPushButton#primary { background: #d4aa7e; color: #252320; border-color: #d4aa7e; font-weight: 600; }
QPushButton#primary:hover { background: #e0b98f; }
QPushButton#primary:disabled { background: #685e52; color: #b2ada6; }
QPushButton#quiet { background: transparent; padding: 5px 10px; border-color: transparent; }
QPushButton#window { background: transparent; border: none; border-radius: 0; padding: 4px; min-width: 29px; }
QPushButton#window:hover { background: #454646; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #2d2f31; border: 1px solid #454646; border-radius: 5px; padding: 9px 11px; min-height: 20px; selection-background-color: #65513e; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView { background: #2d2f31; selection-background-color: #514334; color: #eeeae5; border: 1px solid #665541; padding: 4px; }
QTableWidget { background: #242628; border: none; border-bottom: 1px solid #454646; gridline-color: #454646; outline: 0; selection-background-color: #413a32; selection-color: #eeeae5; }
QTableWidget::item { padding: 9px 13px; border-bottom: 1px solid #454646; }
QTableWidget::item:selected { background: #413a32; }
QHeaderView::section { background: #242628; color: #b2ada6; border: none; border-bottom: 1px solid #454646; padding: 10px 13px; font-size: 11px; }
QCheckBox { spacing: 12px; background: transparent; padding: 7px 0; }
QCheckBox::indicator { width: 28px; height: 16px; border-radius: 8px; background: #555754; border: 1px solid #555754; }
QCheckBox::indicator:checked { background: #d4aa7e; border-color: #d4aa7e; image: none; }
QCheckBox::indicator:unchecked { background: #454646; }
QTabWidget::pane { border: 1px solid #454646; border-radius: 5px; }
QTabBar::tab { padding: 11px 20px; color: #b2ada6; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #d4aa7e; border-bottom-color: #d4aa7e; }
QScrollArea { border: none; }
QScrollBar:vertical { width: 10px; background: #242628; }
QScrollBar::handle:vertical { background: #555754; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #353737; border: none; border-radius: 3px; height: 7px; text-align: center; }
QProgressBar::chunk { background: #d4aa7e; border-radius: 3px; }
QToolTip { background: #2d2f31; color: #eeeae5; border: 1px solid #d4aa7e; padding: 7px; }
"""
