"""Desktopové GUI (PySide6) pro dávkové odspikování Ramanových spekter."""
from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("QT_API", "pyside6")

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from .batch import DespikeParams, process_folder, process_folder_consensus
from .despike import despike_spectrum
from .io_loaders import Spectrum, list_spectra_files, load_any, write_txt

APP_NAME = "Raman Despiker"


# --------------------------------------------------------------------------- #
# Dávkové zpracování v samostatném vlákně (aby GUI nezamrzlo)
# --------------------------------------------------------------------------- #
class BatchWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int, str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, input_dir, output_dir, params, recursive, use_consensus=False):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.params = params
        self.recursive = recursive
        self.use_consensus = use_consensus

    @QtCore.Slot()
    def run(self):
        try:
            def cb(done, total, msg):
                self.progress.emit(done, total, msg)

            if self.use_consensus:
                summary = process_folder_consensus(
                    self.input_dir, self.output_dir, self.params,
                    recursive=self.recursive, progress=cb,
                )
            else:
                summary = process_folder(
                    self.input_dir, self.output_dir, self.params,
                    recursive=self.recursive, progress=cb,
                )
            self.finished.emit(summary)
        except Exception:
            self.failed.emit(traceback.format_exc())


# --------------------------------------------------------------------------- #
# Hlavní okno
# --------------------------------------------------------------------------- #
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 720)

        self.input_dir: str | None = None
        self.files: list[str] = []
        self.current_specs: list[Spectrum] = []
        self._thread: QtCore.QThread | None = None
        self._worker: BatchWorker | None = None
        # ruční úpravy: klíč (source, index) -> set indexů (v pořadí dle x) k odstranění
        self._manual: dict[tuple, set] = {}

        self._build_ui()

    # ---- UI ---------------------------------------------------------------- #
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)

        # --- levý panel: soubory + parametry ---
        left = QtWidgets.QVBoxLayout()
        root.addLayout(left, 0)

        self.btn_open = QtWidgets.QPushButton("📂  Otevřít složku…")
        self.btn_open.clicked.connect(self.open_folder)
        left.addWidget(self.btn_open)

        self.chk_recursive = QtWidgets.QCheckBox("Včetně podsložek")
        left.addWidget(self.chk_recursive)

        left.addWidget(QtWidgets.QLabel("Spektra ve složce:"))
        self.list_files = QtWidgets.QListWidget()
        self.list_files.currentRowChanged.connect(self.on_file_selected)
        self.list_files.setMinimumWidth(300)
        left.addWidget(self.list_files, 1)

        # výběr spektra pro .wdf mapy (více spekter v souboru)
        self.spec_row = QtWidgets.QHBoxLayout()
        self.spec_row.addWidget(QtWidgets.QLabel("Spektrum:"))
        self.spin_spec = QtWidgets.QSpinBox()
        self.spin_spec.setMinimum(1)
        self.spin_spec.setMaximum(1)
        self.spin_spec.valueChanged.connect(self.update_preview)
        self.spec_row.addWidget(self.spin_spec)
        self.lbl_spec_count = QtWidgets.QLabel("/ 1")
        self.spec_row.addWidget(self.lbl_spec_count)
        self.spec_row.addStretch(1)
        left.addLayout(self.spec_row)

        left.addWidget(self._build_param_box())

        # --- pravý panel: graf ---
        right = QtWidgets.QVBoxLayout()
        root.addLayout(right, 1)

        self.figure = Figure(figsize=(7, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        toolbar = NavigationToolbar(self.canvas, self)
        right.addWidget(toolbar)
        right.addWidget(self.canvas, 1)
        self.canvas.mpl_connect("button_press_event", self.on_canvas_click)

        hint = QtWidgets.QLabel(
            "Tip: levý klik do grafu ručně odstraní zbylý spike, pravý klik úpravu vrátí."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        right.addWidget(hint)

        # zobrazovací přepínače
        show_row = QtWidgets.QHBoxLayout()
        self.chk_orig = QtWidgets.QCheckBox("Původní")
        self.chk_orig.setChecked(True)
        self.chk_clean = QtWidgets.QCheckBox("Vyčištěné")
        self.chk_clean.setChecked(True)
        self.chk_marks = QtWidgets.QCheckBox("Označit spiky")
        self.chk_marks.setChecked(True)
        for c in (self.chk_orig, self.chk_clean, self.chk_marks):
            c.stateChanged.connect(self.redraw)
            show_row.addWidget(c)
        show_row.addStretch(1)
        self.lbl_spike_count = QtWidgets.QLabel("")
        show_row.addWidget(self.lbl_spike_count)
        right.addLayout(show_row)

        # --- konsenzuální režim ---
        self.chk_consensus = QtWidgets.QCheckBox(
            "Opakovaná měření téhož vzorku — konsenzuální režim (spolehlivější)"
        )
        self.chk_consensus.setToolTip(
            "Pro složku, kde je více měření TÉHOŽ vzorku na stejné ose X. Spiky se "
            "poznají porovnáním se skupinovým mediánem (dopadají náhodně, v mediánu "
            "nejsou). Nejspolehlivější varianta. NEpoužívej pro směs různých vzorků."
        )
        right.addWidget(self.chk_consensus)

        # --- spodní lišta: zpracovat + progress ---
        bottom = QtWidgets.QHBoxLayout()
        self.btn_save_one = QtWidgets.QPushButton("💾  Uložit zobrazené…")
        self.btn_save_one.setToolTip(
            "Uloží právě zobrazené vyčištěné spektrum (včetně ručních úprav) do .txt."
        )
        self.btn_save_one.clicked.connect(self.save_current)
        self.btn_save_one.setEnabled(False)
        bottom.addWidget(self.btn_save_one)
        self.btn_process = QtWidgets.QPushButton("⚙  Zpracovat vše a uložit…")
        self.btn_process.clicked.connect(self.process_all)
        self.btn_process.setEnabled(False)
        bottom.addWidget(self.btn_process)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        bottom.addWidget(self.progress, 1)
        right.addLayout(bottom)

        self.status = self.statusBar()
        self.status.showMessage("Vyber složku se spektry.")

        # data náhledu
        self._preview = None  # (x, y, cleaned, mask)

    def _build_param_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Parametry odspikování")
        form = QtWidgets.QFormLayout(box)

        # threshold s posuvníkem
        self.spin_thr = QtWidgets.QDoubleSpinBox()
        self.spin_thr.setRange(2.0, 30.0)
        self.spin_thr.setSingleStep(0.5)
        self.spin_thr.setValue(6.0)
        self.spin_thr.setToolTip(
            "Práh citlivosti. Nižší = citlivější (chytí i menší spiky, ale roste "
            "riziko falešných detekcí). Typicky 5-8."
        )
        self.slider_thr = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_thr.setRange(20, 300)  # 2.0 - 30.0 (x10)
        self.slider_thr.setValue(60)
        self.spin_thr.valueChanged.connect(
            lambda v: self.slider_thr.setValue(int(round(v * 10)))
        )
        self.slider_thr.valueChanged.connect(
            lambda v: self.spin_thr.setValue(v / 10.0)
        )
        self.spin_thr.valueChanged.connect(self.update_preview)
        thr_row = QtWidgets.QHBoxLayout()
        thr_row.addWidget(self.spin_thr)
        thr_row.addWidget(self.slider_thr, 1)
        thr_w = QtWidgets.QWidget()
        thr_w.setLayout(thr_row)
        form.addRow("Práh (citlivost):", thr_w)

        self.spin_width = QtWidgets.QSpinBox()
        self.spin_width.setRange(1, 15)
        self.spin_width.setValue(5)
        self.spin_width.setToolTip(
            "Maximální šířka spiku v bodech. Delší souvislý útvar se považuje za "
            "reálný pás a nemaže se. Chrání reálné píky (na tomto přístroji mají "
            "reálné pásy >= ~7 bodů, spiky <= ~5)."
        )
        self.spin_width.valueChanged.connect(self.update_preview)
        form.addRow("Max. šířka spiku (px):", self.spin_width)

        self.spin_iter = QtWidgets.QSpinBox()
        self.spin_iter.setRange(1, 10)
        self.spin_iter.setValue(5)
        self.spin_iter.setToolTip("Počet iterací (odhalí menší spiky vedle velkých).")
        self.spin_iter.valueChanged.connect(self.update_preview)
        form.addRow("Iterace:", self.spin_iter)

        self.spin_kernel = QtWidgets.QSpinBox()
        self.spin_kernel.setRange(3, 21)
        self.spin_kernel.setSingleStep(2)
        self.spin_kernel.setValue(5)
        self.spin_kernel.setToolTip("Okno klouzavého mediánu (odhad pozadí).")
        self.spin_kernel.valueChanged.connect(self.update_preview)
        form.addRow("Okno mediánu:", self.spin_kernel)

        self.chk_adaptive = QtWidgets.QCheckBox("Lokálně adaptivní práh")
        self.chk_adaptive.setChecked(True)
        self.chk_adaptive.setToolTip(
            "Přizpůsobí citlivost lokální úrovni šumu (doporučeno)."
        )
        self.chk_adaptive.stateChanged.connect(self.update_preview)
        form.addRow("", self.chk_adaptive)

        self.btn_reset = QtWidgets.QPushButton("Výchozí hodnoty")
        self.btn_reset.clicked.connect(self.reset_params)
        form.addRow("", self.btn_reset)

        return box

    # ---- parametry --------------------------------------------------------- #
    def current_params(self) -> DespikeParams:
        return DespikeParams(
            threshold=self.spin_thr.value(),
            med_kernel=self.spin_kernel.value(),
            width_cap=self.spin_width.value(),
            iterations=self.spin_iter.value(),
            adaptive=self.chk_adaptive.isChecked(),
            adapt_window=151,
        )

    def reset_params(self):
        self.spin_thr.setValue(6.0)
        self.spin_width.setValue(5)
        self.spin_iter.setValue(5)
        self.spin_kernel.setValue(5)
        self.chk_adaptive.setChecked(True)

    # ---- akce -------------------------------------------------------------- #
    def open_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Vyber složku se spektry", self.input_dir or ""
        )
        if not folder:
            return
        self.input_dir = folder
        self.files = list_spectra_files(folder, recursive=self.chk_recursive.isChecked())
        self.list_files.clear()
        for p in self.files:
            self.list_files.addItem(os.path.basename(p))
        if self.files:
            self.list_files.setCurrentRow(0)
            self.btn_process.setEnabled(True)
            self.status.showMessage(f"Nalezeno souborů: {len(self.files)}")
        else:
            self.btn_process.setEnabled(False)
            self.status.showMessage("Ve složce nejsou žádná podporovaná spektra (.txt / .wdf).")
            self.ax.clear()
            self.canvas.draw_idle()

    def on_file_selected(self, row: int):
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        try:
            self.current_specs = load_any(path)
        except Exception as e:
            self.current_specs = []
            self.status.showMessage(f"Chyba načtení: {e}")
            self.ax.clear()
            self.canvas.draw_idle()
            return
        n = len(self.current_specs)
        self.spin_spec.blockSignals(True)
        self.spin_spec.setMaximum(max(1, n))
        self.spin_spec.setValue(1)
        self.spin_spec.blockSignals(False)
        self.lbl_spec_count.setText(f"/ {n}")
        self.spin_spec.setEnabled(n > 1)
        self.update_preview()

    def _current_spectrum(self) -> Spectrum | None:
        if not self.current_specs:
            return None
        idx = min(self.spin_spec.value() - 1, len(self.current_specs) - 1)
        return self.current_specs[idx]

    def _spec_key(self, spec: Spectrum) -> tuple:
        return (spec.source, spec.index)

    def update_preview(self):
        spec = self._current_spectrum()
        if spec is None:
            return
        p = self.current_params()
        x = np.asarray(spec.x, float)
        y = np.asarray(spec.y, float)
        try:
            _x, cleaned, auto_mask = despike_spectrum(x, y, **p.as_kwargs())
        except Exception as e:
            self.status.showMessage(f"Chyba výpočtu: {e}")
            return

        # ruční úpravy
        manual = self._manual.get(self._spec_key(spec), set())
        combined = auto_mask.copy()
        n_manual = 0
        if manual:
            manual_arr = np.zeros(len(x), dtype=bool)
            for i in manual:
                if 0 <= i < len(x):
                    manual_arr[i] = True
            combined = auto_mask | manual_arr
            order = np.argsort(x)
            inv = np.argsort(order)
            cs = cleaned[order]
            cm = combined[order]
            good = ~cm
            if good.sum() >= 2 and cm.any():
                pos = np.arange(len(x))
                cs[cm] = np.interp(pos[cm], pos[good], cs[good])
            cleaned = cs[inv]
            n_manual = int(manual_arr.sum())

        self._preview = (x, y, cleaned, combined)
        self.lbl_spike_count.setText(
            f"Spiků: {int(combined.sum())}" + (f"  (ruční: {n_manual})" if n_manual else "")
        )
        self.btn_save_one.setEnabled(True)
        self.redraw()

    def on_canvas_click(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        spec = self._current_spectrum()
        if spec is None:
            return
        x = np.asarray(spec.x, float)
        y = np.asarray(spec.y, float)
        k = int(np.argmin(np.abs(x - event.xdata)))
        ms = self._manual.setdefault(self._spec_key(spec), set())
        if event.button == 1:  # levý klik: odstraň nejbližší lokální maximum
            lo, hi = max(0, k - 3), min(len(x), k + 4)
            kk = lo + int(np.argmax(y[lo:hi]))
            ms.add(kk)
        elif event.button == 3:  # pravý klik: vrať ruční úpravu v okolí
            for i in [j for j in ms if abs(j - k) <= 3]:
                ms.discard(i)
        self.update_preview()

    def save_current(self):
        if self._preview is None:
            return
        spec = self._current_spectrum()
        x, y, cleaned, mask = self._preview
        default = os.path.join(self.input_dir or "", f"{spec.name}_despiked.txt")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Uložit zobrazené spektrum", default, "Text (*.txt)"
        )
        if not path:
            return
        try:
            write_txt(path, x, cleaned)
            self.status.showMessage(f"Uloženo: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"Chyba uložení:\n{e}")

    def redraw(self):
        if self._preview is None:
            return
        x, y, cleaned, mask = self._preview
        self.ax.clear()
        if self.chk_orig.isChecked():
            self.ax.plot(x, y, lw=0.8, color="#c0392b", alpha=0.55, label="Původní")
        if self.chk_clean.isChecked():
            self.ax.plot(x, cleaned, lw=0.9, color="#1f6f3f", label="Vyčištěné")
        if self.chk_marks.isChecked() and mask.any():
            self.ax.scatter(
                x[mask], y[mask], s=28, facecolors="none", edgecolors="#c0392b",
                linewidths=1.3, label="Detekované spiky", zorder=5,
            )
        spec = self._current_spectrum()
        title = spec.name if spec else ""
        self.ax.set_title(title, fontsize=10)
        self.ax.set_xlabel("Ramanův posun (cm⁻¹)")
        self.ax.set_ylabel("Intenzita")
        if x.size and x[0] > x[-1]:
            self.ax.invert_xaxis()  # Renishaw bývá sestupně
        self.ax.legend(loc="best", fontsize=8)
        self.ax.grid(True, alpha=0.2)
        self.canvas.draw_idle()

    def process_all(self):
        if not self.input_dir or not self.files:
            return
        default_out = os.path.join(self.input_dir, "despiked")
        out = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Vyber složku pro uložení vyčištěných spekter", default_out
        )
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.input_dir):
            QtWidgets.QMessageBox.warning(
                self, APP_NAME,
                "Výstupní složka nesmí být stejná jako vstupní (přepsala by data). "
                "Vyber prosím jinou složku.",
            )
            return

        params = self.current_params()
        recursive = self.chk_recursive.isChecked()

        self.btn_process.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)

        self._thread = QtCore.QThread()
        self._worker = BatchWorker(
            self.input_dir, out, params, recursive,
            use_consensus=self.chk_consensus.isChecked(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._out_dir = out
        self._thread.start()

    def _on_progress(self, done, total, msg):
        self.progress.setValue(done)
        self.status.showMessage(f"Zpracovávám {done}/{total}: {msg}")

    def _cleanup_thread(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
        self.btn_process.setEnabled(True)
        self.btn_open.setEnabled(True)
        self.progress.setVisible(False)

    def _on_finished(self, summary):
        self._cleanup_thread()
        msg = (
            f"Hotovo. Souborů: {summary.n_files}  |  OK: {summary.n_ok}  |  "
            f"Chyb: {summary.n_failed}  |  Odstraněno spiků celkem: {summary.total_spikes}"
        )
        self.status.showMessage(msg)
        detail = ""
        if summary.n_failed:
            detail = "\n\nChybné soubory:\n" + "\n".join(
                f"• {os.path.basename(r.source)}: {r.error}"
                for r in summary.results if not r.ok
            )
        QtWidgets.QMessageBox.information(
            self, APP_NAME,
            f"{msg}\n\nUloženo do:\n{self._out_dir}{detail}",
        )

    def _on_failed(self, tb):
        self._cleanup_thread()
        self.status.showMessage("Zpracování selhalo.")
        QtWidgets.QMessageBox.critical(self, APP_NAME, f"Chyba při zpracování:\n\n{tb}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
