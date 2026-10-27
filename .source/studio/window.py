import json
import os
import shutil
import sys
import uuid
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QProcess, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ascii_exporter import QUALITY_PRESET_MAP, sanitize_video_folder_name
from studio.model import StudioSettings, application_paths, load_settings, resource_path, save_json, save_settings
from studio.surfaces import VideoTable, WindowSurface
from studio.theme import STYLE
from studio.translations import translate

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}


class StudioCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#b2ada6" if self.isEnabled() else "#777976"))
        middle = self.height() // 2
        edge = self.width() - 14
        painter.drawLine(QPoint(edge - 4, middle - 2), QPoint(edge, middle + 2))
        painter.drawLine(QPoint(edge, middle + 2), QPoint(edge + 4, middle - 2))


def make_combo(items):
    combo = StudioCombo()
    for label, value in items:
        combo.addItem(label, value)
    combo.setMaxVisibleItems(15)
    return combo


def set_combo(combo, value):
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


class Switch(QCheckBox):
    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#eeeae5" if self.isEnabled() else "#777976"))
        painter.drawText(self.rect().adjusted(0, 0, -44, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        track = QRectF(self.width() - 32, (self.height() - 18) / 2, 30, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d4aa7e" if self.isChecked() else "#454646"))
        painter.drawRoundedRect(track, 9, 9)
        painter.setBrush(QColor("#242628" if self.isChecked() else "#9d9d98"))
        thumb_left = track.left() + (15 if self.isChecked() else 3)
        painter.drawEllipse(QRectF(thumb_left, track.top() + 3, 12, 12))
        if self.hasFocus():
            painter.setPen(QColor("#d4aa7e"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)


class TitleBar(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()


class AdvancedDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setStyleSheet(STYLE)
        self.resize(720, 600)
        self.setMinimumSize(530, 440)
        self.controls = {}
        self.text_labels = []
        outer = QVBoxLayout(self)
        language_row = QHBoxLayout()
        language_row.addStretch()
        self.language = make_combo([("TR", "tr"), ("EN", "en")])
        set_combo(self.language, owner.settings.language)
        self.language.currentIndexChanged.connect(lambda: owner.set_language(self.language.currentData()))
        language_row.addWidget(self.language)
        outer.addLayout(language_row)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        forms = []
        for _ in range(3):
            page = QWidget()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            form = QFormLayout(page)
            form.setContentsMargins(22, 20, 22, 20)
            form.setVerticalSpacing(18)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            forms.append(form)
            self.tabs.addTab(scroll, "")

        self.add_number(forms[0], "cols", "columns", 0, 450, "columns_hint")
        self.add_text(forms[0], "char_ramp", "ramp", "ramp_hint")
        self.add_number(forms[0], "font_size", "font", 0, 48)
        self.add_number(forms[0], "fps", "fps", 0, 60, decimals=2)
        self.add_number(forms[0], "char_aspect", "aspect", 0.1, 2, "aspect_hint", decimals=2)
        self.add_text(forms[0], "custom_resolution", "custom_resolution", "custom_resolution_hint")
        self.add_number(forms[1], "seek_step", "seek", 1, 600)
        self.add_check(forms[1], "hud", "hud", "hud_hint")
        self.add_check(forms[1], "audio", "sound", "audio_hint")
        self.add_check(forms[1], "crt", "crt", "crt_hint")
        self.add_check(forms[1], "loop", "loop")
        note = QLabel()
        note.setObjectName("muted")
        note.setWordWrap(True)
        self.text_labels.append((note, "note_speed"))
        forms[1].addRow(note)
        encoder = make_combo([(value, value) for value in
                              ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow")])
        self.add_control(forms[2], "encoder_preset", "encoder", encoder)
        self.add_number(forms[2], "workers", "workers", 0, 32)
        self.add_number(forms[2], "crf", "crf", 0, 51, "crf_hint")
        self.add_text(forms[2], "output_root", "output")
        browse = QPushButton()
        self.text_labels.append((browse, "browse"))
        browse.clicked.connect(self.browse_output)
        forms[2].addRow(browse)
        buttons = QHBoxLayout()
        reset = QPushButton()
        self.text_labels.append((reset, "reset"))
        reset.clicked.connect(lambda: self.populate(StudioSettings(language=owner.settings.language)))
        cancel = QPushButton()
        self.text_labels.append((cancel, "cancel"))
        cancel.clicked.connect(self.reject)
        apply = QPushButton()
        apply.setObjectName("primary")
        self.text_labels.append((apply, "apply"))
        apply.clicked.connect(self.apply_settings)
        buttons.addWidget(reset)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(apply)
        outer.addLayout(buttons)
        self.populate(owner.current_settings())
        self.retranslate()

    def add_control(self, form, key, label_key, control, hint=None):
        self.controls[key] = control
        label = QLabel()
        self.text_labels.append((label, label_key))
        if hint:
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            layout.addWidget(control)
            explanation = QLabel()
            explanation.setObjectName("muted")
            explanation.setWordWrap(True)
            self.text_labels.append((explanation, hint))
            layout.addWidget(explanation)
            form.addRow(label, container)
        else:
            form.addRow(label, control)

    def add_number(self, form, key, label_key, minimum, maximum, hint=None, decimals=0):
        control = QDoubleSpinBox() if decimals else QSpinBox()
        control.setRange(minimum, maximum)
        if decimals:
            control.setDecimals(decimals)
            control.setSingleStep(0.05)
        self.add_control(form, key, label_key, control, hint)

    def add_text(self, form, key, label_key, hint=None):
        self.add_control(form, key, label_key, QLineEdit(), hint)

    def add_check(self, form, key, label_key, hint=None):
        self.add_control(form, key, label_key, QCheckBox(), hint)

    def populate(self, settings):
        for key, control in self.controls.items():
            value = getattr(settings, key, "")
            if key == "custom_resolution":
                value = settings.resolution if "x" in settings.resolution else ""
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QComboBox):
                set_combo(control, value)
            elif isinstance(control, QLineEdit):
                control.setText(value)
            else:
                control.setValue(value)

    def retranslate(self):
        tr = self.owner.tr_key
        self.setWindowTitle(tr("advanced"))
        for widget, key in self.text_labels:
            widget.setText(tr(key))
        for index, key in enumerate(("appearance", "playback", "encoding")):
            self.tabs.setTabText(index, tr(key))
        self.language.blockSignals(True)
        set_combo(self.language, self.owner.settings.language)
        self.language.blockSignals(False)
        for key in ("cols", "font_size", "workers", "fps"):
            self.controls[key].setSpecialValueText(tr("auto"))

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, self.owner.tr_key("output"), str(self.owner.paths["output"]))
        if path:
            self.controls["output_root"].setText(path)

    def apply_settings(self):
        data = asdict(self.owner.current_settings())
        for key, control in self.controls.items():
            if key == "custom_resolution":
                if control.text().strip():
                    data["resolution"] = control.text().strip().lower()
            elif isinstance(control, QCheckBox):
                data[key] = control.isChecked()
            elif isinstance(control, QComboBox):
                data[key] = control.currentData()
            elif isinstance(control, QLineEdit):
                data[key] = control.text()
            else:
                data[key] = control.value()
        try:
            self.owner.settings = StudioSettings(**data).validate()
        except ValueError as error:
            QMessageBox.warning(self, self.owner.tr_key("settings_error"), str(error))
            return
        self.owner.apply_settings_to_controls()
        self.owner.persist()
        self.accept()


class StudioWindow(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "seguisb.ttf", "bahnschrift.ttf", "consola.ttf"):
            path = fonts / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        self.paths = application_paths(root)
        for key in ("videos", "output", "state"):
            self.paths[key].mkdir(parents=True, exist_ok=True)
        self.settings_path = self.paths["state"] / "settings.json"
        self.settings = load_settings(self.settings_path)
        self.files = []
        self.process = None
        self.play_processes = []
        self.progress_file = None
        self.active_request = None
        self.advanced_dialog = None
        self.last_stage = "ready"
        self.setWindowTitle("ASCII Studio")
        self.setObjectName("studioWindow")
        self.setWindowIcon(QIcon(str(resource_path("assets/eye_icon.ico"))))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(800, 620)
        self.resize(1048, 740)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1048, available.width() - 30), min(740, available.height() - 40))
            self.move(available.center() - self.rect().center())
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self.text_labels = []
        container = WindowSurface()
        container.setObjectName("shell")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(container)
        titlebar = TitleBar()
        titlebar.setObjectName("titlebar")
        titlebar.setFixedHeight(47)
        title_layout = QHBoxLayout(titlebar)
        title_layout.setContentsMargins(22, 0, 8, 0)
        symbol = QLabel("[%]")
        symbol.setObjectName("symbol")
        title_layout.addWidget(symbol)
        brand = QLabel("ASCII / STUDIO")
        brand.setObjectName("brand")
        title_layout.addWidget(brand)
        title_layout.addStretch()
        self.language = make_combo([("TR", "tr"), ("EN", "en")])
        self.language.setFixedWidth(68)
        self.language.setAccessibleName("Language / Dil")
        self.language.currentIndexChanged.connect(lambda: self.set_language(self.language.currentData()))
        title_layout.addWidget(self.language)
        for text, callback in (("—", self.showMinimized), ("□", self.toggle_maximized), ("×", self.close)):
            button = QPushButton(text)
            button.setObjectName("window")
            button.clicked.connect(callback)
            title_layout.addWidget(button)
        outer.addWidget(titlebar)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(28, 25, 28, 22)
        content.setSpacing(18)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        self.heading = self.label("heading", "heading")
        titles.addWidget(self.heading)
        top.addLayout(titles)
        top.addStretch()
        self.folder_button = self.button("folder", self.add_folder)
        self.add_button = self.button("add", self.choose_files)
        top.addWidget(self.folder_button)
        top.addWidget(self.add_button)
        content.addLayout(top)
        self.table = VideoTable(0, 3)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 140)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.doubleClicked.connect(lambda: self.start_job("play"))
        content.addWidget(self.table, 1)
        self.empty_label = self.label("empty", "muted")
        content.addWidget(self.empty_label)
        inspector = QHBoxLayout()
        inspector.setSpacing(25)
        self.inspector_widget = QWidget()
        self.inspector_widget.setLayout(inspector)
        inspector.setContentsMargins(0, 3, 0, 0)
        columns = []
        for key in ("appearance", "video_section", "options"):
            column = QVBoxLayout()
            column.setSpacing(9)
            column.addWidget(self.label(key, "section"))
            columns.append(column)
            inspector.addLayout(column, 1)
        self.quality = make_combo([(f"{key}. {value['id'].upper()}", key) for key, value in QUALITY_PRESET_MAP.items()])
        self.color = make_combo([])
        self.resolution = make_combo([])
        self.fps = make_combo([])
        self.add_field(columns[0], "quality", self.quality)
        self.add_field(columns[0], "color", self.color)
        self.add_field(columns[1], "resolution", self.resolution)
        self.add_field(columns[1], "fps", self.fps)
        self.audio = Switch()
        self.crt = Switch()
        self.loop = Switch()
        for switch in (self.audio, self.crt, self.loop):
            switch.setMinimumHeight(37)
        for key, widget in (("sound", self.audio), ("crt", self.crt), ("loop", self.loop)):
            self.text_labels.append((widget, key))
            columns[2].addWidget(widget)
        columns[2].addStretch()
        content.addWidget(self.inspector_widget)
        info = QHBoxLayout()
        self.help_label = self.label("help", "muted")
        self.help_label.setWordWrap(True)
        info.addWidget(self.help_label, 1)
        self.advanced_button = self.button("advanced", self.show_advanced)
        self.advanced_button.setObjectName("quiet")
        info.addWidget(self.advanced_button)
        content.addLayout(info)
        self.progress_panel = QWidget()
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        status_row = QHBoxLayout()
        self.stage_label = QLabel()
        self.percent_label = QLabel("0%")
        self.cancel_button = self.button("cancel", self.cancel_job)
        self.cancel_button.setObjectName("quiet")
        status_row.addWidget(self.stage_label, 1)
        status_row.addWidget(self.percent_label)
        status_row.addWidget(self.cancel_button)
        progress_layout.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        progress_layout.addWidget(self.progress)
        self.progress_panel.hide()
        content.addWidget(self.progress_panel)
        outer.addWidget(body, 1)
        footer = QWidget()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(26, 15, 12, 15)
        self.path_label = QLabel()
        self.path_label.setObjectName("muted")
        self.path_label.setWordWrap(True)
        footer_layout.addWidget(self.path_label, 1)
        self.output_button = self.button("open_output", self.open_output)
        self.output_button.setObjectName("quiet")
        self.play_button = self.button("play", lambda: self.start_job("play"))
        self.export_button = self.button("export", lambda: self.start_job("export"))
        self.render_button = self.button("render", lambda: self.start_job("render"))
        self.render_button.setObjectName("primary")
        for button in (self.output_button, self.play_button, self.export_button, self.render_button):
            footer_layout.addWidget(button)
        footer_layout.addWidget(QSizeGrip(self))
        outer.addWidget(footer)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll_progress)
        self.apply_settings_to_controls()
        self.retranslate()
        for widget in (self.quality, self.color, self.resolution, self.fps):
            widget.currentIndexChanged.connect(self.settings_changed)
        for widget in (self.audio, self.crt, self.loop):
            widget.toggled.connect(self.settings_changed)
        initial_files = list(self.paths["videos"].iterdir()) + list(self.paths["root"].glob("*.mp4"))
        self.add_files(initial_files)

    def tr_key(self, key):
        return translate(key, self.settings.language)

    def label(self, key, object_name=None):
        label = QLabel()
        if object_name:
            label.setObjectName(object_name)
        self.text_labels.append((label, key))
        return label

    def button(self, key, callback):
        button = QPushButton()
        self.text_labels.append((button, key))
        button.clicked.connect(callback)
        return button

    def add_field(self, layout, key, control):
        label = self.label(key, "muted")
        layout.addWidget(label)
        layout.addWidget(control)

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self.setProperty("maximized", self.isMaximized())
            self.setStyleSheet(STYLE)
            if self.centralWidget():
                self.centralWidget().update()
        super().changeEvent(event)

    def current_settings(self):
        return replace(self.settings, quality=self.quality.currentData() or self.settings.quality,
                       color_mode=self.color.currentData() or self.settings.color_mode,
                       resolution=self.resolution.currentData() or self.settings.resolution,
                       fps=self.fps.currentData() if self.fps.currentData() is not None else self.settings.fps,
                       audio=self.audio.isChecked(), crt=self.crt.isChecked(), loop=self.loop.isChecked())

    def apply_settings_to_controls(self):
        widgets = (self.language, self.quality, self.color, self.resolution, self.fps, self.audio, self.crt, self.loop)
        for widget in widgets:
            widget.blockSignals(True)
        set_combo(self.language, self.settings.language)
        set_combo(self.quality, self.settings.quality)
        self.populate_translated_combos()
        self.audio.setChecked(self.settings.audio)
        self.crt.setChecked(self.settings.crt)
        self.loop.setChecked(self.settings.loop)
        for widget in widgets:
            widget.blockSignals(False)

    def populate_translated_combos(self):
        for combo, items, selected in (
            (self.color, [(self.tr_key(key), value) for key, value in
                          (("original", "truecolor"), ("gray", "grayscale"), ("green", "green"),
                           ("amber", "amber"), ("cyberpunk", "cyberpunk"))], self.settings.color_mode),
            (self.resolution, [(self.tr_key("auto"), "auto"), ("720p · 1280 × 720", "720p"),
                               ("1080p · 1920 × 1080", "1080p"), ("2K · 2560 × 1440", "2k"),
                               ("4K · 3840 × 2160", "4k"), (self.tr_key("grid"), "original")], self.settings.resolution),
            (self.fps, [(self.tr_key("source"), 0)] + [(f"{rate} FPS", rate) for rate in (12, 15, 24, 25, 30, 48, 50, 60)], self.settings.fps),
        ):
            combo.blockSignals(True)
            combo.clear()
            for label, value in items:
                combo.addItem(label, value)
            if combo.findData(selected) < 0:
                combo.addItem(str(selected), selected)
            set_combo(combo, selected)
            combo.blockSignals(False)

    def set_language(self, language):
        if language not in ("tr", "en"):
            return
        self.settings = replace(self.current_settings(), language=language)
        self.language.blockSignals(True)
        set_combo(self.language, language)
        self.language.blockSignals(False)
        self.retranslate()
        if self.advanced_dialog:
            self.advanced_dialog.retranslate()
        self.persist()

    def retranslate(self):
        for widget, key in self.text_labels:
            widget.setText(self.tr_key(key))
        for index, (key, value) in enumerate(QUALITY_PRESET_MAP.items()):
            self.quality.setItemText(index, f"{key}. {value['id'].upper()} · {value['cols']} {self.tr_key('units_columns')}")
        self.populate_translated_combos()
        self.table.setHorizontalHeaderLabels([self.tr_key(key) for key in ("file", "type", "selection")])
        self.selection_changed()
        self.stage_label.setText(self.tr_key(self.last_stage))
        self.audio.setToolTip(self.tr_key("audio_hint"))
        self.crt.setToolTip(self.tr_key("crt_hint"))

    def settings_changed(self):
        self.settings = self.current_settings()
        self.persist()
        self.selection_changed()

    def persist(self):
        try:
            save_settings(self.settings_path, self.settings)
        except (OSError, ValueError):
            self.path_label.setText(self.tr_key("save_error"))

    def selected_video(self):
        row = self.table.currentRow()
        return self.files[row] if 0 <= row < len(self.files) else None

    def add_files(self, paths):
        first_new = len(self.files)
        for path in paths:
            path = Path(path).resolve()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and path not in self.files:
                self.files.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(path.name))
                self.table.item(row, 0).setToolTip(str(path))
                self.table.setItem(row, 1, QTableWidgetItem(path.suffix[1:].upper()))
                self.table.setItem(row, 2, QTableWidgetItem(""))
        if len(self.files) > first_new:
            self.table.selectRow(first_new)
        self.empty_label.setVisible(not self.files)
        self.selection_changed()

    def selection_changed(self):
        for row in range(self.table.rowCount()):
            self.table.item(row, 2).setText(self.tr_key("selected") if row == self.table.currentRow() else "—")
        video = self.selected_video()
        output = Path(self.settings.output_root) if self.settings.output_root else self.paths["output"]
        self.path_label.setText(f"{video.name} → {output / sanitize_video_folder_name(str(video))}" if video else self.tr_key("choose"))
        busy = self.process is not None
        for button in (self.play_button, self.export_button, self.render_button):
            button.setEnabled(bool(video) and not busy)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.tr_key("add"), str(self.paths["videos"]),
                                               "Video (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v)")
        self.add_files(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr_key("folder"), str(self.paths["videos"]))
        if folder:
            self.add_files(Path(folder).iterdir())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            paths.extend(path.iterdir() if path.is_dir() else [path])
        self.add_files(paths)
        event.acceptProposedAction()

    def create_advanced_dialog(self):
        self.advanced_dialog = AdvancedDialog(self)
        return self.advanced_dialog

    def show_advanced(self):
        self.create_advanced_dialog().exec()
        self.advanced_dialog = None

    def make_request(self, action):
        video = self.selected_video()
        if not video:
            raise ValueError(self.tr_key("choose"))
        settings = self.current_settings().validate()
        output_root = Path(settings.output_root) if settings.output_root else self.paths["output"]
        stem = sanitize_video_folder_name(str(video))
        folder = output_root / stem
        output = folder / (f"{stem}_ascii.mp4" if action == "render" else f"{stem}.exe")
        return {"action": action, "video": str(video), "output": str(output), "settings": asdict(settings)}

    def confirm(self, message):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self.tr_key("title"))
        dialog.setText(message)
        yes = dialog.addButton(self.tr_key("yes"), QMessageBox.ButtonRole.YesRole)
        no = dialog.addButton(self.tr_key("no"), QMessageBox.ButtonRole.NoRole)
        dialog.setDefaultButton(no)
        dialog.exec()
        return dialog.clickedButton() == yes

    def start_job(self, action):
        if self.process:
            return
        try:
            request = self.make_request(action)
        except ValueError as error:
            QMessageBox.warning(self, self.tr_key("settings_error"), str(error))
            return
        if action != "play" and Path(request["output"]).exists() and not self.confirm(self.tr_key("overwrite")):
            return
        job_dir = self.paths["state"] / "jobs" / uuid.uuid4().hex
        job_dir.mkdir(parents=True)
        request["progress"] = str(job_dir / "progress.json")
        request["log"] = str(job_dir / "worker.log")
        request_path = job_dir / "request.json"
        save_json(request_path, request)
        process = QProcess(self)
        if getattr(sys, "frozen", False):
            process.setProgram(sys.executable)
            process.setArguments(["--worker", str(request_path)])
        else:
            process.setProgram(sys.executable)
            process.setArguments([str(resource_path("studio_main.py")), "--worker", str(request_path)])
        process.setWorkingDirectory(str(self.paths["root"]))
        if action == "play":
            self.play_processes.append(process)
            process.finished.connect(lambda: self.play_processes.remove(process) if process in self.play_processes else None)
            process.errorOccurred.connect(lambda: QMessageBox.warning(self, self.tr_key("error"), process.errorString()))
            process.start()
            return
        self.process = process
        self.active_request = request
        self.cancel_requested = False
        self.progress_file = Path(request["progress"])
        self.last_stage = "starting"
        self.stage_label.setText(self.tr_key("starting"))
        self.progress.setValue(0)
        self.percent_label.setText("0%")
        self.progress_panel.show()
        self.inspector_widget.setEnabled(False)
        self.advanced_button.setEnabled(False)
        self.table.setEnabled(False)
        self.add_button.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.selection_changed()
        process.finished.connect(self.job_finished)
        process.errorOccurred.connect(self.process_error)
        self.timer.start()
        process.start()

    def poll_progress(self):
        if not self.progress_file:
            return
        try:
            data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        percent = max(0, min(100, float(data.get("percent", 0))))
        self.progress.setValue(round(percent * 10))
        self.percent_label.setText(f"{percent:.1f}%")
        self.last_stage = data.get("stage", "starting")
        text = self.tr_key(self.last_stage)
        if data.get("total"):
            text += f" · {data.get('current', 0)} / {data['total']} {self.tr_key('frames')}"
        if data.get("fps"):
            text += f" · {data['fps']:.1f} FPS · {self.tr_key('eta')} ~{data.get('eta', 0):.0f}s"
        self.stage_label.setText(text)

    def process_error(self, error):
        if self.process and error == QProcess.ProcessError.FailedToStart:
            message = self.process.errorString()
            self.job_finished(-1)
            QMessageBox.warning(self, self.tr_key("error"), message)

    def job_finished(self, exit_code, exit_status=None):
        self.timer.stop()
        self.poll_progress()
        process = self.process
        self.process = None
        for widget in (self.inspector_widget, self.advanced_button, self.table, self.add_button, self.folder_button):
            widget.setEnabled(True)
        self.selection_changed()
        data = {}
        try:
            data = json.loads(self.progress_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            pass
        if exit_code == 0 and data.get("success") and Path(self.active_request["output"]).is_file():
            self.last_stage = "finished"
            self.stage_label.setText(self.tr_key("finished"))
            self.progress.setValue(1000)
            self.percent_label.setText("100%")
        elif self.cancel_requested:
            self.last_stage = "cancelled"
            self.stage_label.setText(self.tr_key("cancelled"))
        else:
            self.stage_label.setText(self.tr_key("error"))
            QMessageBox.warning(self, self.tr_key("error"), data.get("error", self.tr_key("error")))
        if process:
            process.deleteLater()
        job_root = Path(self.active_request["progress"]).parent.resolve()
        expected_root = (self.paths["state"] / "jobs").resolve()
        if job_root.is_relative_to(expected_root):
            for partial in job_root.glob(".ascii-export-*"):
                if partial.resolve().is_relative_to(job_root) and partial.is_dir():
                    shutil.rmtree(partial, ignore_errors=True)
            partial_render = job_root / "render.mp4"
            if partial_render.is_file():
                partial_render.unlink(missing_ok=True)

    def cancel_job(self):
        if self.process:
            self.cancel_requested = True
            self.last_stage = "cancelled"
            self.process.kill()

    def open_output(self):
        folder = Path(self.settings.output_root) if self.settings.output_root else self.paths["output"]
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event):
        if self.process:
            if not self.confirm(self.tr_key("close_busy")):
                event.ignore()
                return
            self.process.kill()
            self.process.waitForFinished(3000)
        self.persist()
        event.accept()
