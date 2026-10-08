"""GUI to rewrite file modification times from dates written in filenames."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from timestamp_parser import CompiledPattern, PatternError, compile_pattern

PRESETS = [
    "yyyy-mm-dd_HH-mm-ss",
    "yyyymmddHHmmss",
    "yyyy-mm-dd HH.mm.ss",
    "yyyy-mm-dd",
    "yyyymmdd",
    "yyyy_mm_dd_HH_mm",
    "dd-mm-yyyy",
    "dd.mm.yyyy",
    "yymmdd",
    "IMG_yyyymmdd_HHmmss",
]

TIME_FMT = "%Y-%m-%d %H:%M:%S"
# Filesystems store mtime with limited resolution; ignore sub-second drift.
SAME_TIME_TOLERANCE = 2.0


@dataclass
class FileRow:
    path: Path
    current: datetime
    new: datetime | None = None
    status: str = ""
    applied: bool = False

    @property
    def matched(self) -> bool:
        return self.new is not None

    @property
    def up_to_date(self) -> bool:
        return (
            self.new is not None
            and abs(self.new.timestamp() - self.current.timestamp()) <= SAME_TIME_TOLERANCE
        )


class ScanWorker(QThread):
    """Walks the folder and parses every filename, off the GUI thread."""

    progress = pyqtSignal(int)
    done = pyqtSignal(list, str)

    def __init__(self, folder: Path, pattern: CompiledPattern, recursive: bool) -> None:
        super().__init__()
        self.folder = folder
        self.pattern = pattern
        self.recursive = recursive
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        rows: list[FileRow] = []
        error = ""
        try:
            for path in self._iter_files():
                if self._stop:
                    break
                try:
                    current = datetime.fromtimestamp(path.stat().st_mtime)
                except OSError:
                    continue
                row = FileRow(path=path, current=current)
                try:
                    row.new = self.pattern.parse(path.name)
                    row.status = "up to date" if row.up_to_date else "ready"
                except ValueError as exc:
                    row.status = str(exc)
                rows.append(row)
                if len(rows) % 200 == 0:
                    self.progress.emit(len(rows))
        except OSError as exc:
            error = str(exc)
        self.done.emit(rows, error)

    def _iter_files(self):
        for dirpath, dirnames, filenames in os.walk(self.folder):
            for name in sorted(filenames):
                yield Path(dirpath) / name
            if not self.recursive:
                dirnames.clear()


class ApplyWorker(QThread):
    """Applies the new modification times, reporting progress per file."""

    progress = pyqtSignal(int)
    result = pyqtSignal(int, bool, str)  # row index, ok, error message
    done = pyqtSignal()

    def __init__(self, jobs: list[tuple[int, Path, datetime]]) -> None:
        super().__init__()
        self.jobs = jobs

    def run(self) -> None:
        for done_count, (index, path, new_dt) in enumerate(self.jobs, start=1):
            try:
                stat = path.stat()
                os.utime(path, (stat.st_atime, new_dt.timestamp()))
                self.result.emit(index, True, "")
            except OSError as exc:
                self.result.emit(index, False, exc.strerror or str(exc))
            self.progress.emit(done_count)
        self.done.emit()


class MainWindow(QMainWindow):
    COL_CHECK, COL_NAME, COL_FOLDER, COL_CURRENT, COL_NEW, COL_STATUS = range(6)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Filename to Modified Date")
        self.resize(1100, 640)

        self.rows: list[FileRow] = []
        self.scan_worker: ScanWorker | None = None
        self.apply_worker: ApplyWorker | None = None
        self.failures: list[str] = []
        self.successes = 0
        self.settings = QSettings("timestamp-gui", "FilenameToMtime")

        self._build_ui()
        self._restore_settings()
        self._update_buttons()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QGridLayout()
        form.setColumnStretch(1, 1)

        form.addWidget(QLabel("Timestamp format:"), 0, 0)
        self.format_box = QComboBox()
        self.format_box.setEditable(True)
        self.format_box.addItems(PRESETS)
        self.format_box.setToolTip(
            "Tokens: yyyy / yy (year), mm (month), dd (day), HH (hour), "
            "mm (minute, when it comes after the hour), ss (second).\n"
            "Use nn or mi to force a minute. Anything else is matched literally, "
            "and the pattern is searched anywhere in the filename."
        )
        self.format_box.currentTextChanged.connect(self._on_format_changed)
        form.addWidget(self.format_box, 0, 1, 1, 2)

        form.addWidget(QLabel("Folder:"), 1, 0)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Folder containing the files to fix")
        self.folder_edit.textChanged.connect(lambda _: self._update_buttons())
        form.addWidget(self.folder_edit, 1, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._choose_folder)
        form.addWidget(browse, 1, 2)

        options = QHBoxLayout()
        self.recursive_check = QCheckBox("Include subfolders")
        self.recursive_check.setChecked(True)
        self.hide_unmatched_check = QCheckBox("Hide files that do not match")
        self.hide_unmatched_check.stateChanged.connect(lambda _: self._populate_table())
        options.addWidget(self.recursive_check)
        options.addWidget(self.hide_unmatched_check)
        options.addStretch(1)
        self.scan_button = QPushButton("Scan folder")
        self.scan_button.clicked.connect(self._scan)
        options.addWidget(self.scan_button)
        form.addLayout(options, 2, 1, 1, 2)

        layout.addLayout(form)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #e05561;")
        self.hint_label.setVisible(False)
        layout.addWidget(self.hint_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "File", "Folder", "Current modified", "New modified", "Status"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_CHECK, 34)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeMode.Stretch)
        for column in (self.COL_CURRENT, self.COL_NEW, self.COL_STATUS):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))
        bottom.addWidget(self.select_all_button)
        bottom.addWidget(self.select_none_button)
        bottom.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(220)
        bottom.addWidget(self.progress)

        self.apply_button = QPushButton("Apply new timestamps")
        apply_font = QFont(self.apply_button.font())
        apply_font.setBold(True)
        self.apply_button.setFont(apply_font)
        self.apply_button.clicked.connect(self._apply)
        bottom.addWidget(self.apply_button)
        layout.addLayout(bottom)

        self.status_label = QLabel("Choose a format and a folder, then scan.")
        layout.addWidget(self.status_label)

        self.setCentralWidget(central)

    # ------------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        self.format_box.setCurrentText(self.settings.value("format", PRESETS[0], type=str))
        self.folder_edit.setText(self.settings.value("folder", "", type=str))
        self.recursive_check.setChecked(self.settings.value("recursive", True, type=bool))

    def closeEvent(self, event) -> None:
        self.settings.setValue("format", self.format_box.currentText())
        self.settings.setValue("folder", self.folder_edit.text())
        self.settings.setValue("recursive", self.recursive_check.isChecked())
        for worker in (self.scan_worker, self.apply_worker):
            if worker is not None and worker.isRunning():
                if isinstance(worker, ScanWorker):
                    worker.stop()
                worker.wait(3000)
        super().closeEvent(event)

    # --------------------------------------------------------------- actions
    def _choose_folder(self) -> None:
        start = self.folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", start)
        if folder:
            self.folder_edit.setText(folder)

    def _on_format_changed(self, text: str) -> None:
        try:
            compile_pattern(text)
        except PatternError as exc:
            self.hint_label.setText(f"Format problem: {exc}")
            self.hint_label.setVisible(True)
        else:
            self.hint_label.setVisible(False)
        self._update_buttons()

    def _current_pattern(self) -> CompiledPattern | None:
        try:
            return compile_pattern(self.format_box.currentText())
        except PatternError:
            return None

    def _scan(self) -> None:
        pattern = self._current_pattern()
        folder = Path(self.folder_edit.text().strip())
        if pattern is None:
            QMessageBox.warning(self, "Invalid format", "Fix the timestamp format first.")
            return
        if not folder.is_dir():
            QMessageBox.warning(self, "Folder not found", f"'{folder}' is not a folder.")
            return

        self.rows = []
        self.table.setRowCount(0)
        self._set_busy(True, "Scanning...")
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)

        self.scan_worker = ScanWorker(folder, pattern, self.recursive_check.isChecked())
        self.scan_worker.progress.connect(
            lambda n: self.status_label.setText(f"Scanning... {n} files")
        )
        self.scan_worker.done.connect(self._scan_finished)
        self.scan_worker.start()

    def _scan_finished(self, rows: list, error: str) -> None:
        self.rows = rows
        self.progress.setVisible(False)
        self._set_busy(False)
        self._populate_table()
        if error:
            QMessageBox.warning(self, "Scan problem", error)

    def _populate_table(self) -> None:
        hide_unmatched = self.hide_unmatched_check.isChecked()
        root = Path(self.folder_edit.text())
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for index, row in enumerate(self.rows):
            if hide_unmatched and not row.matched:
                continue
            table_row = self.table.rowCount()
            self.table.insertRow(table_row)

            selectable = row.matched and not row.applied
            check = QTableWidgetItem()
            check.setData(Qt.ItemDataRole.UserRole, index)
            flags = Qt.ItemFlag.ItemIsEnabled
            if selectable:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            check.setFlags(flags)
            checked = selectable and not row.up_to_date
            check.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.table.setItem(table_row, self.COL_CHECK, check)

            try:
                folder_text = str(row.path.parent.relative_to(root))
            except ValueError:
                folder_text = str(row.path.parent)
            values = {
                self.COL_NAME: row.path.name,
                self.COL_FOLDER: folder_text,
                self.COL_CURRENT: row.current.strftime(TIME_FMT),
                self.COL_NEW: row.new.strftime(TIME_FMT) if row.new else "-",
                self.COL_STATUS: row.status,
            }
            for column, text in values.items():
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, index)
                if not row.matched:
                    item.setForeground(QColor("#8a8a8a"))
                elif row.applied:
                    item.setForeground(QColor("#4caf50"))
                self.table.setItem(table_row, column, item)

        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self._update_summary()

    def _set_all_checked(self, checked: bool) -> None:
        self.table.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for table_row in range(self.table.rowCount()):
            item = self.table.item(table_row, self.COL_CHECK)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(state)
        self.table.blockSignals(False)
        self._update_summary()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self.COL_CHECK:
            self._update_summary()

    def _checked_jobs(self) -> list[tuple[int, Path, datetime]]:
        jobs = []
        for table_row in range(self.table.rowCount()):
            item = self.table.item(table_row, self.COL_CHECK)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            index = item.data(Qt.ItemDataRole.UserRole)
            row = self.rows[index]
            if row.new is not None and not row.applied:
                jobs.append((index, row.path, row.new))
        return jobs

    def _apply(self) -> None:
        jobs = self._checked_jobs()
        if not jobs:
            return
        answer = QMessageBox.question(
            self,
            "Confirm",
            f"Write a new 'last modified' timestamp on {len(jobs)} file(s)?\n"
            "This changes the files on disk and cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, f"Applying to {len(jobs)} file(s)...")
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.failures = []
        self.successes = 0

        self.apply_worker = ApplyWorker(jobs)
        self.apply_worker.progress.connect(self.progress.setValue)
        self.apply_worker.result.connect(self._apply_result)
        self.apply_worker.done.connect(self._apply_finished)
        self.apply_worker.start()

    def _apply_result(self, index: int, ok: bool, error: str) -> None:
        row = self.rows[index]
        if ok:
            row.applied = True
            row.current = row.new
            row.status = "updated"
            self.successes += 1
        else:
            row.status = f"failed: {error}"
            self.failures.append(f"{row.path}: {error}")

    def _apply_finished(self) -> None:
        self.progress.setVisible(False)
        self._set_busy(False)
        self._populate_table()
        if self.failures:
            shown = "\n".join(self.failures[:15])
            extra = "" if len(self.failures) <= 15 else f"\n... and {len(self.failures) - 15} more"
            QMessageBox.warning(
                self,
                "Some files could not be updated",
                f"Updated {self.successes} file(s).\n\nFailures:\n{shown}{extra}",
            )
        else:
            QMessageBox.information(self, "Done", f"Updated {self.successes} file(s).")

    # --------------------------------------------------------------- helpers
    def _set_busy(self, busy: bool, message: str = "") -> None:
        for widget in (
            self.scan_button,
            self.apply_button,
            self.format_box,
            self.folder_edit,
            self.recursive_check,
            self.select_all_button,
            self.select_none_button,
        ):
            widget.setEnabled(not busy)
        if message:
            self.status_label.setText(message)
        if not busy:
            self._update_buttons()

    def _update_buttons(self) -> None:
        ready = bool(self.folder_edit.text().strip()) and self._current_pattern() is not None
        self.scan_button.setEnabled(ready)
        self.apply_button.setEnabled(bool(self._checked_jobs()))

    def _update_summary(self) -> None:
        if not self.rows:
            self.status_label.setText("No files scanned yet.")
            self._update_buttons()
            return
        matched = sum(1 for row in self.rows if row.matched)
        selected = len(self._checked_jobs())
        self.status_label.setText(
            f"{len(self.rows)} file(s) found - {matched} match the format - "
            f"{len(self.rows) - matched} skipped - {selected} selected"
        )
        self.apply_button.setText(
            f"Apply to {selected} file(s)" if selected else "Apply new timestamps"
        )
        self._update_buttons()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Filename to Modified Date")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
