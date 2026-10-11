"""Divide Reader desktop app (PySide6).

Tabs: 1. Model (start screen) -> 2. Read -> Manual count -> Compare.
Logins live only in memory (auth.Session) until the window closes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import __version__, auth, download, ingest, jobs, measures, paths, report
from ..connect import Connection, connect, ollama_models, openrouter_models
from ..i18n import T
from ..localserver import downloaded_models
from ..providers.base import ModelSpec
from ..providers.catalog import LOCAL_MODELS, PROVIDERS, recommend_local
from ..reader import Budget, Reader


# --- settings (no secrets here) ---------------------------------------------

def load_settings() -> dict:
    try:
        return json.loads(paths.config_file().read_text())
    except (OSError, ValueError):
        return {}


def save_settings(s: dict) -> None:
    paths.config_file().write_text(json.dumps(s, indent=2))


# --- background work -----------------------------------------------------------

class Worker(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            self.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:  # noqa: BLE001 - shown to the user
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


def run_bg(owner: QObject, fn, *args, on_done=None, on_fail=None, **kwargs):
    th = QThread(owner)
    w = Worker(fn, *args, **kwargs)
    w.moveToThread(th)
    th.started.connect(w.run)
    if on_done:
        w.done.connect(on_done)
    if on_fail:
        w.failed.connect(on_fail)
    w.done.connect(th.quit)
    w.failed.connect(th.quit)
    th.finished.connect(w.deleteLater)
    th.finished.connect(th.deleteLater)
    owner._workers = getattr(owner, "_workers", []) + [(th, w)]
    th.start()
    return w


def note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)
    return lab


# --- 1. Model -------------------------------------------------------------------

class ModelTab(QWidget):
    connected = Signal(object, object)  # Connection, ProviderSpec
    dl_progress = Signal(int, int)

    def __init__(self, t: T, session: auth.Session, settings: dict):
        super().__init__()
        self.t, self.session, self.settings = t, session, settings
        self.conn: Connection | None = None
        self.dl_cancel: threading.Event | None = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)

        title = QLabel(f"<h2>{t('choose_model')}</h2>")
        lay.addWidget(title)

        # Explicit, at the top: the JSON guarantee and direct download links.
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(box)
        bl.addWidget(note(t("json_guarantee")))
        ram = download.total_ram_gb()
        rec = recommend_local(ram)
        bl.addWidget(note(t("local_links", ram=ram, rec=rec.label)))
        grid = QGridLayout()
        self.dl_buttons: dict[str, QPushButton] = {}
        for i, m in enumerate(LOCAL_MODELS):
            grid.addWidget(note(f"<a href='{m.url}'>{m.label}</a> · {m.size / 1e9:.1f} GB · {m.licence} · "
                                f"<a href='{m.page}'>page</a>"), i, 0)
            b = QPushButton(t("downloaded") if download.is_downloaded(m) else t("download"))
            b.setEnabled(not download.is_downloaded(m))
            b.clicked.connect(lambda _=False, mm=m: self.start_download(mm))
            grid.addWidget(b, i, 1)
            self.dl_buttons[m.id] = b
        bl.addLayout(grid)
        self.dl_bar = QProgressBar()
        self.dl_bar.hide()
        self.dl_progress.connect(lambda a, b: self.dl_bar.setValue(int(1000 * a / max(b, 1))))
        bl.addWidget(self.dl_bar)
        lay.addWidget(box)

        self.group = QButtonGroup(self)

        # Built-in
        g_local = QGroupBox()
        gl = QHBoxLayout(g_local)
        self.r_local = QRadioButton(t("grp_local"))
        self.local_combo = QComboBox()
        gl.addWidget(self.r_local)
        gl.addWidget(self.local_combo, 1)
        lay.addWidget(g_local)

        # Ollama
        g_ol = QGroupBox()
        ol = QHBoxLayout(g_ol)
        self.r_ollama = QRadioButton(t("grp_ollama"))
        self.ollama_combo = QComboBox()
        b_ref = QPushButton(t("refresh"))
        b_ref.clicked.connect(self.load_ollama)
        ol.addWidget(self.r_ollama)
        ol.addWidget(self.ollama_combo, 1)
        ol.addWidget(b_ref)
        lay.addWidget(g_ol)

        # Online groups
        self.online: dict[str, dict] = {}
        for group in ("free", "paid"):
            g = QGroupBox()
            fl = QFormLayout(g)
            r = QRadioButton(t(f"grp_{group}"))
            fl.addRow(r)
            prov = QComboBox()
            for p in PROVIDERS:
                if p.group == group:
                    prov.addItem(p.label, p.id)
            if group == "paid":
                prov.addItem("OpenRouter", "openrouter")  # after Claude, OpenAI and Grok
            model = QComboBox()
            model.setEditable(True)
            status = QLabel(t("not_logged_in"))
            b_login = QPushButton(t("login"))
            row = QHBoxLayout()
            row.addWidget(b_login)
            row.addWidget(status, 1)
            fl.addRow(t("provider"), prov)
            fl.addRow(t("model"), model)
            if group == "paid":
                pin, pout = QDoubleSpinBox(), QDoubleSpinBox()
                for sp in (pin, pout):
                    sp.setDecimals(3)
                    sp.setRange(0, 1000)
                pr = QHBoxLayout()
                pr.addWidget(pin)
                pr.addWidget(QLabel("/"))
                pr.addWidget(pout)
                fl.addRow(t("price"), pr)
            else:
                pin = pout = None
            fl.addRow(row)
            lay.addWidget(g)
            self.online[group] = {"radio": r, "prov": prov, "model": model, "status": status, "login": b_login,
                                  "pin": pin, "pout": pout}
            prov.currentIndexChanged.connect(lambda _=0, gr=group: self.fill_models(gr))
            model.currentIndexChanged.connect(lambda _=0, gr=group: self.fill_price(gr))
            b_login.clicked.connect(lambda _=False, gr=group: self.login(gr))

        for r in (self.r_local, self.r_ollama, self.online["free"]["radio"], self.online["paid"]["radio"]):
            self.group.addButton(r)
        lay.addWidget(note(f"<i>{t('login_note')}</i>"))

        actions = QHBoxLayout()
        self.b_test = QPushButton(t("test3"))
        self.b_use = QPushButton(t("use_model"))
        self.b_use.setDefault(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        actions.addWidget(self.b_test)
        actions.addWidget(self.b_use)
        lay.addLayout(actions)
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.b_use.clicked.connect(lambda: self.connect_model(test=False))
        self.b_test.clicked.connect(lambda: self.connect_model(test=True))

        self.fill_local()
        self.load_ollama()
        for gr in self.online:
            self.fill_models(gr)
        last = settings.get("group", "local")
        {"local": self.r_local, "ollama": self.r_ollama}.get(last, self.online.get(last, {}).get("radio",
                                                                                                  self.r_local)).setChecked(True)

    # -- lists
    def fill_local(self):
        self.local_combo.clear()
        files = downloaded_models()
        if not files:
            self.local_combo.addItem(self.t("no_local"), None)
        for f in files:
            self.local_combo.addItem(f.name, str(f))

    def load_ollama(self):
        self.ollama_combo.clear()
        try:
            for name in ollama_models():
                self.ollama_combo.addItem(name, name)
        except Exception:  # noqa: BLE001 - Ollama simply not running
            self.ollama_combo.addItem("(Ollama not running)", None)

    def spec_of(self, group: str):
        from ..providers.catalog import provider
        return provider(self.online[group]["prov"].currentData())

    def fill_models(self, group: str):
        o = self.online[group]
        spec = self.spec_of(group)
        o["model"].blockSignals(True)
        o["model"].clear()
        models = list(spec.models)
        if spec.id == "openrouter":
            try:
                live = openrouter_models(self.session.get("openrouter"))
                live = [m for m in live if m.free] if group == "free" else [m for m in live if not m.free]
                known = {m.id for m in models} if group == "free" else set()
                models = (models if group == "free" else []) + sorted(
                    (m for m in live if m.id not in known), key=lambda m: m.id)
            except Exception:  # noqa: BLE001 - offline: keep the built-in list
                pass
        for m in models:
            o["model"].addItem(m.label if m.label != m.id else m.id, m)
        o["model"].blockSignals(False)
        o["status"].setText(self.t("logged_in") if self.session.logged_in(spec.id) else self.t("not_logged_in"))
        self.fill_price(group)

    def fill_price(self, group: str):
        o = self.online[group]
        if o["pin"] is None:
            return
        m = o["model"].currentData()
        saved = self.settings.get("prices", {}).get(m.id if isinstance(m, ModelSpec) else "", None)
        pin = saved[0] if saved else (m.price_in if isinstance(m, ModelSpec) and m.price_in is not None else 0)
        pout = saved[1] if saved else (m.price_out if isinstance(m, ModelSpec) and m.price_out is not None else 0)
        o["pin"].setValue(pin)
        o["pout"].setValue(pout)

    # -- downloads
    def start_download(self, m):
        self.dl_cancel = threading.Event()
        self.dl_bar.show()
        self.dl_bar.setRange(0, 1000)
        self.dl_buttons[m.id].setEnabled(False)
        run_bg(self, download.download, m, self.dl_progress.emit, self.dl_cancel,
               on_done=lambda p: self._dl_done(m), on_fail=lambda e: self._dl_fail(m, e))

    def _dl_done(self, m):
        self.dl_bar.hide()
        self.dl_buttons[m.id].setText(self.t("downloaded"))
        self.fill_local()
        self.r_local.setChecked(True)

    def _dl_fail(self, m, e):
        self.dl_bar.hide()
        self.dl_buttons[m.id].setEnabled(True)
        QMessageBox.warning(self, self.t("error"), e)

    # -- login: always through the default browser
    def login(self, group: str) -> bool:
        spec = self.spec_of(group)
        o = self.online[group]
        if spec.login == "pkce":
            o["status"].setText(self.t("waiting_login"))
            QApplication.processEvents()
            try:
                key = auth.openrouter_login()
            except Exception as e:  # noqa: BLE001
                o["status"].setText(self.t("test_fail", e=e))
                return False
            self.session.set(spec.id, key)
        else:
            auth.open_key_page(spec)
            key, ok = QInputDialog.getText(self, spec.label, self.t("paste_key", url=spec.key_url),
                                           QLineEdit.Password)
            if not ok or not key.strip():
                return False
            self.session.set(spec.id, key)
        o["status"].setText(self.t("logged_in"))
        if spec.id == "openrouter":
            self.fill_models(group)
        return True

    # -- connect
    def current(self):
        if self.r_local.isChecked():
            return "local", None
        if self.r_ollama.isChecked():
            return "ollama", None
        for g, o in self.online.items():
            if o["radio"].isChecked():
                return g, o
        return "local", None

    def connect_model(self, test: bool):
        group, o = self.current()
        from ..providers.catalog import provider
        if group == "local":
            path = self.local_combo.currentData()
            if not path:
                QMessageBox.information(self, self.t("error"), self.t("no_local"))
                return
            spec, model = provider("local"), ModelSpec(path, Path(path).name, free=True)
        elif group == "ollama":
            name = self.ollama_combo.currentData()
            if not name:
                return
            spec, model = provider("ollama"), ModelSpec(name, name, free=True)
        else:
            spec = self.spec_of(group)
            model = o["model"].currentData()
            text = o["model"].currentText().strip()
            if not isinstance(model, ModelSpec) or (text and text != model.label and text != model.id):
                model = ModelSpec(text, text, free=group == "free")
            if group == "paid":
                model = ModelSpec(model.id, model.label, o["pin"].value(), o["pout"].value(), free=False)
                self.settings.setdefault("prices", {})[model.id] = [model.price_in, model.price_out]
            if not self.session.logged_in(spec.id) and not self.login(group):
                return
        self.settings["group"] = group
        save_settings(self.settings)
        if self.conn:
            self.conn.close()
            self.conn = None
        self.status.setText(self.t("connecting"))
        self.b_use.setEnabled(False)
        self.b_test.setEnabled(False)
        run_bg(self, self._connect_and_test, spec, model, test,
               on_done=lambda r: self._connected(r, spec, test), on_fail=self._connect_failed)

    def _connect_and_test(self, spec, model, test):
        conn = connect(spec, model, self.session)
        n = None
        if test:
            n = run_test(conn)
        return conn, n

    def _connected(self, r, spec, test):
        self.conn, n = r
        self.b_use.setEnabled(True)
        self.b_test.setEnabled(True)
        msg = self.t("connected", m=self.conn.provider.label)
        if test:
            msg += " · " + self.t("test_ok", n=n)
        self.status.setText(msg)
        self.connected.emit(self.conn, spec)

    def _connect_failed(self, e):
        self.b_use.setEnabled(True)
        self.b_test.setEnabled(True)
        self.status.setText(self.t("test_fail", e=e))


TEST_TEXT = ("Sindikat, vlada i poslodavci opet su se dogovorili preko leđa radnika. "
             "The government and the employers agreed while the workers waited outside. "
             "Ja sam napravio website za naš mali klub i svi su bili zadovoljni rezultatom.")


def run_test(conn: Connection) -> int:
    """Read three sentences end to end in a throwaway store."""
    import tempfile
    from ..store import Store
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.txt"
        p.write_text(TEST_TEXT + " " + "Ovo je dodatak da tekst bude dovoljno dug za čistač.", encoding="utf-8")
        st = Store(Path(d) / "s.sqlite")
        sid, units = ingest.ingest_file(st, p)
        reader = Reader(st, conn.provider, Budget(st, "test", None), log=lambda s: None)
        for u in units[:3]:
            reader.read_unit(u)
        n = sum(len(r.readings) for r in (measures.load_unit(st, u) for u in units[:3]) if r)
        st.close()
        return n


# --- 2. Read --------------------------------------------------------------------

class ReadTab(QWidget):
    job_log = Signal(str)
    job_progress = Signal(str, int, int)

    def __init__(self, t: T, settings: dict, lang: str):
        super().__init__()
        self.t, self.settings, self.lang = t, settings, lang
        self.conn: Connection | None = None
        self.spec = None
        self.stop = threading.Event()
        self.last_report: Path | None = None
        lay = QVBoxLayout(self)
        self.model_label = QLabel(t("need_model"))
        lay.addWidget(self.model_label)
        form = QFormLayout()
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("https://…  /  ~/knjiga.pdf")
        b = QPushButton(t("browse"))
        b.clicked.connect(self.browse)
        row.addWidget(self.input, 1)
        row.addWidget(b)
        form.addRow(t("input"), row)
        self.mode = QComboBox()
        for k in ("auto", "file", "page", "list", "wander", "wayback"):
            self.mode.addItem(t(f"mode_{k}"), k)
        self.year = QSpinBox()
        self.year.setRange(1996, 2100)
        self.year.setValue(2005)
        mr = QHBoxLayout()
        mr.addWidget(self.mode, 1)
        mr.addWidget(QLabel(t("year")))
        mr.addWidget(self.year)
        form.addRow(t("mode"), mr)
        self.unit = QComboBox()
        for k in ("sentence", "paragraph", "article", "chapter"):
            self.unit.addItem(t(f"unit_{k}"), k)
        form.addRow(t("unit_kind"), self.unit)
        self.sample = QSpinBox()
        self.sample.setRange(0, 100000)
        self.sample.setValue(200)
        form.addRow(t("sample_n"), self.sample)
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 5000)
        self.max_pages.setValue(30)
        self.max_hops = QSpinBox()
        self.max_hops.setRange(0, 20)
        self.max_hops.setValue(3)
        pr = QHBoxLayout()
        pr.addWidget(self.max_pages)
        pr.addWidget(QLabel(t("max_hops")))
        pr.addWidget(self.max_hops)
        form.addRow(t("max_pages"), pr)
        self.cap = QDoubleSpinBox()
        self.cap.setRange(0, 100000)
        self.cap.setDecimals(2)
        self.cap.setValue(float(settings.get("cap", 5.0)))
        form.addRow(t("cost_cap"), self.cap)
        self.hyp = QCheckBox(t("do_hyp"))
        self.hyp.setChecked(True)
        form.addRow(self.hyp)
        lay.addLayout(form)
        self.est = QLabel("")
        lay.addWidget(self.est)
        for w in (self.sample,):
            w.valueChanged.connect(self.update_estimate)
        btns = QHBoxLayout()
        self.b_start = QPushButton(t("start"))
        self.b_stop = QPushButton(t("stop"))
        self.b_resume = QPushButton(t("resume"))
        self.b_open = QPushButton(t("open_report"))
        self.b_stop.setEnabled(False)
        self.b_open.setEnabled(False)
        for b in (self.b_start, self.b_stop, self.b_resume, self.b_open):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        self.job_log.connect(self.log.appendPlainText)
        self.job_progress.connect(lambda st, i, n: (self.bar.setRange(0, n), self.bar.setValue(i)))
        self.b_start.clicked.connect(lambda: self.start(resume=False))
        self.b_resume.clicked.connect(lambda: self.start(resume=True))
        self.b_stop.clicked.connect(self.stop.set)
        self.b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report))))
        self.set_enabled(False)

    def set_enabled(self, on: bool):
        for w in (self.b_start, self.b_resume):
            w.setEnabled(on)

    def set_connection(self, conn: Connection, spec):
        self.conn, self.spec = conn, spec
        self.model_label.setText(self.t("connected", m=conn.provider.label))
        self.cap.setEnabled(spec.group == "paid" or not conn.provider.model.free)
        self.set_enabled(True)
        self.update_estimate()

    def update_estimate(self):
        n = self.sample.value() or 200
        m = self.conn.provider.model if self.conn else None
        e = jobs.estimate(n, price_in=getattr(m, "price_in", None), price_out=getattr(m, "price_out", None))
        cost = f", ~${e['cost_usd']:.2f}" if e["cost_usd"] is not None else ""
        self.est.setText(self.t("estimate", calls=e["calls"], tok=(e["in_tokens"] + e["out_tokens"]) // 1000,
                                cost=cost))

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, self.t("browse"), str(Path.home()),
                                           "Texts (*.pdf *.epub *.txt *.md *.html *.htm);;All (*)")
        if f:
            self.input.setText(f)

    def start(self, resume: bool):
        if not self.conn:
            QMessageBox.information(self, "", self.t("need_model"))
            return
        paid = not self.conn.provider.model.free
        cap = self.cap.value() if self.cap.isEnabled() else None
        if paid and not cap:
            QMessageBox.information(self, "", self.t("need_cap"))
            return
        self.settings["cap"] = self.cap.value()
        save_settings(self.settings)
        source_id = None
        if resume:
            store = jobs.open_store(jobs.project_dir())
            js = jobs.list_jobs(store)
            store.close()
            if not js:
                return
            last = js[0]
            spec = jobs.JobSpec(**last["spec"])
            spec.cost_cap = cap
            source_id = last["source_id"]
        else:
            text = self.input.text().strip()
            if not text:
                return
            spec = jobs.JobSpec(input=str(Path(text).expanduser()) if not text.startswith("http") else text,
                                input_kind=self.mode.currentData(), unit_kind=self.unit.currentData(),
                                sample=self.sample.value() or None, max_pages=self.max_pages.value(),
                                max_hops=self.max_hops.value(),
                                wayback_year=self.year.value() if self.mode.currentData() == "wayback" else None,
                                cost_cap=cap, hypotheses=self.hyp.isChecked(), report_lang=self.lang)
        self.stop.clear()
        self.log.clear()
        self.b_start.setEnabled(False)
        self.b_resume.setEnabled(False)
        self.b_stop.setEnabled(True)
        run_bg(self, self._run, spec, source_id, on_done=self.finished, on_fail=self.failed)

    def _run(self, spec, source_id):
        return jobs.run(spec, self.conn.provider, log=self.job_log.emit, progress=self.job_progress.emit,
                        stop=self.stop, source_id=source_id)

    def finished(self, res):
        self.b_stop.setEnabled(False)
        self.set_enabled(True)
        self.last_report = res.report
        self.b_open.setEnabled(res.report is not None)
        self.log.appendPlainText(self.t("done", n=res.units_read, why=res.stopped_reason))

    def failed(self, e):
        self.b_stop.setEnabled(False)
        self.set_enabled(True)
        self.log.appendPlainText(f"{self.t('error')}: {e}")


# --- Manual count -------------------------------------------------------------------

class ManualTab(QWidget):
    """Count by hand: figures, then sort them into sides; each set of sides is one reading."""

    def __init__(self, t: T, settings: dict):
        super().__init__()
        self.t, self.settings = t, settings
        self.units: list[int] = []
        self.pos = 0
        self.readings: list[tuple[int, ...]] = []
        self.conn: Connection | None = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.annot = QLineEdit(settings.get("annotator", ""))
        self.source = QComboBox()
        b_load = QPushButton(t("load_units"))
        b_file = QPushButton(t("add_file"))
        top.addWidget(QLabel(t("annotator")))
        top.addWidget(self.annot)
        top.addWidget(QLabel(t("sources")))
        top.addWidget(self.source, 1)
        top.addWidget(b_load)
        top.addWidget(b_file)
        lay.addLayout(top)
        self.pos_label = QLabel("")
        lay.addWidget(self.pos_label)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setStyleSheet("font-size: 17px; padding: 8px;")
        lay.addWidget(self.text)
        fr = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel(t("figures_edit")))
        self.figs = QPlainTextEdit()
        self.figs.setMaximumHeight(140)
        self.figs.textChanged.connect(self.rebuild_sides)
        left.addWidget(self.figs)
        self.b_model_figs = QPushButton(t("model_figures"))
        left.addWidget(self.b_model_figs)
        fr.addLayout(left, 1)
        mid = QVBoxLayout()
        mid.addWidget(QLabel(t("side_of")))
        self.side_box = QWidget()
        self.side_grid = QFormLayout(self.side_box)
        mid.addWidget(self.side_box)
        b_add = QPushButton(t("add_reading"))
        mid.addWidget(b_add)
        mid.addStretch(1)
        fr.addLayout(mid, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel(t("your_readings")))
        self.rlist = QListWidget()
        right.addWidget(self.rlist)
        b_rm = QPushButton(t("remove"))
        right.addWidget(b_rm)
        fr.addLayout(right, 1)
        lay.addLayout(fr)
        self.role = QLabel("")
        lay.addWidget(self.role)
        nav = QHBoxLayout()
        b_prev, b_save, b_next = QPushButton(t("prev")), QPushButton(t("save")), QPushButton(t("next"))
        b_cov = QPushButton(t("coverage"))
        for b in (b_prev, b_save, b_next, b_cov):
            nav.addWidget(b)
        lay.addLayout(nav)
        self.msg = QLabel("")
        lay.addWidget(self.msg)
        lay.addStretch(1)
        b_load.clicked.connect(self.load_units)
        b_file.clicked.connect(self.add_file)
        b_add.clicked.connect(self.add_reading)
        b_rm.clicked.connect(self.remove_reading)
        b_prev.clicked.connect(lambda: self.go(-1))
        b_next.clicked.connect(lambda: self.go(1))
        b_save.clicked.connect(self.save)
        b_cov.clicked.connect(self.coverage)
        self.b_model_figs.clicked.connect(self.model_figures)
        self.side_combos: list[QComboBox] = []
        self.refresh_sources()

    def store(self):
        return jobs.open_store(jobs.project_dir())

    def refresh_sources(self):
        st = self.store()
        self.source.clear()
        for r in st.q("SELECT id, label FROM source ORDER BY id DESC"):
            self.source.addItem(f"#{r['id']} {r['label']}", r["id"])
        st.close()

    def add_file(self):
        f, _ = QFileDialog.getOpenFileName(self, self.t("add_file"), str(Path.home()),
                                           "Texts (*.pdf *.epub *.txt *.md *.html *.htm);;All (*)")
        if not f:
            return
        st = self.store()
        ingest.ingest_file(st, f)
        st.close()
        self.refresh_sources()

    def load_units(self):
        sid = self.source.currentData()
        if sid is None:
            self.msg.setText(self.t("no_units"))
            return
        st = self.store()
        self.units = measures.sample_units(measures.source_units(st, sid), 100)
        st.close()
        self.pos = 0
        self.show_unit()

    @staticmethod
    def role_for(unit_id: int) -> str:
        """Half of the counted units become examples, half are kept for checking (fixed per unit)."""
        return "example" if int(hashlib.sha1(str(unit_id).encode()).hexdigest(), 16) % 2 == 0 else "check"

    def show_unit(self):
        if not self.units:
            self.msg.setText(self.t("no_units"))
            return
        uid = self.units[self.pos]
        st = self.store()
        u = st.one("SELECT text FROM unit WHERE id=?", (uid,))
        figs = st.locked_figures(uid)
        saved = st.one("SELECT rkeys, s_values FROM manual WHERE unit_id=? AND annotator=?",
                       (uid, self.annot.text().strip() or "me"))
        st.close()
        self.pos_label.setText(f"{self.pos + 1} / {len(self.units)} · #{uid}")
        self.text.setText(u["text"])
        self.figs.blockSignals(True)
        self.figs.setPlainText("\n".join(figs or []))
        self.figs.blockSignals(False)
        self.readings = []
        if saved and saved["rkeys"]:
            from .. import partitions as P
            self.readings = [P.parse_key(k) for k in json.loads(saved["rkeys"])]
        self.rebuild_sides()
        self.refresh_readings()
        role = self.role_for(uid)
        self.role.setText(f"{self.t('role')}: {self.t('role_' + role)}")

    def fig_list(self) -> list[str]:
        return [f.strip() for f in self.figs.toPlainText().splitlines() if f.strip()]

    def rebuild_sides(self):
        while self.side_grid.rowCount():
            self.side_grid.removeRow(0)
        self.side_combos = []
        figs = self.fig_list()
        for f in figs:
            c = QComboBox()
            for i in range(len(figs)):
                c.addItem(f"{self.t('side_of')} {i + 1}", i)
            self.side_grid.addRow(f, c)
            self.side_combos.append(c)

    def add_reading(self):
        from .. import partitions as P
        labels = [c.currentData() for c in self.side_combos]
        rgs = P.normalize(labels) if labels else ()
        if rgs not in self.readings:
            self.readings.append(rgs)
        self.refresh_readings()

    def remove_reading(self):
        i = self.rlist.currentRow()
        if 0 <= i < len(self.readings):
            self.readings.pop(i)
            self.refresh_readings()

    def refresh_readings(self):
        from .. import partitions as P
        self.rlist.clear()
        figs = self.fig_list()
        for rgs in self.readings:
            names = figs if len(figs) == len(rgs) else [f"f{i}" for i in range(len(rgs))]
            self.rlist.addItem(QListWidgetItem(f"S = {P.sides(rgs)}   {P.describe(rgs, names) if rgs else '∅'}"))

    def save(self):
        from .. import partitions as P
        if not self.units:
            return
        uid = self.units[self.pos]
        who = self.annot.text().strip() or "me"
        self.settings["annotator"] = who
        save_settings(self.settings)
        if not self.readings:
            self.readings = [tuple([0] * 0)] if not self.fig_list() else self.readings
        s_values = sorted({P.sides(r) for r in self.readings})
        st = self.store()
        st.db.execute("""INSERT OR REPLACE INTO manual (unit_id, annotator, role, s_values, rkeys, note, created)
                         VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))""",
                      (uid, who, self.role_for(uid), json.dumps(s_values),
                       json.dumps([P.key(r) for r in self.readings]), "figures: " + "; ".join(self.fig_list())))
        st.commit()
        st.close()
        self.msg.setText(self.t("saved"))

    def go(self, d: int):
        if not self.units:
            return
        self.pos = max(0, min(len(self.units) - 1, self.pos + d))
        self.msg.setText("")
        self.show_unit()

    def coverage(self):
        st = self.store()
        r = measures.manual_check(st, self.annot.text().strip() or None)
        st.close()
        cov = "—" if r["coverage"] is None else f"{r['coverage'] * 100:.0f}%"
        exc = "—" if r["excess"] is None else f"{r['excess'] * 100:.0f}%"
        self.msg.setText(self.t("coverage_res", cov=cov, exc=exc, n=r["n_units"]))

    def model_figures(self):
        if not self.conn or not self.units:
            self.msg.setText(self.t("need_model"))
            return
        uid = self.units[self.pos]

        def work():
            st = self.store()
            r = Reader(st, self.conn.provider, Budget(st, "manual", None))
            figs = r.lock_figures(uid)
            st.close()
            return figs
        run_bg(self, work, on_done=lambda figs: self.figs.setPlainText("\n".join(figs)),
               on_fail=lambda e: self.msg.setText(e))


# --- Compare ------------------------------------------------------------------------

class CompareTab(QWidget):
    def __init__(self, t: T, lang: str):
        super().__init__()
        self.t, self.lang = t, lang
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(t("sources")))
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_ref = QPushButton(t("refresh"))
        b_rep = QPushButton(t("open_report"))
        b_cmp = QPushButton(t("make_compare"))
        row.addWidget(b_ref)
        row.addWidget(b_rep)
        row.addWidget(b_cmp)
        lay.addLayout(row)
        self.msg = QLabel("")
        lay.addWidget(self.msg)
        b_ref.clicked.connect(self.refresh)
        b_cmp.clicked.connect(self.compare)
        b_rep.clicked.connect(self.one_report)
        self.refresh()

    def refresh(self):
        self.list.clear()
        st = jobs.open_store(jobs.project_dir())
        for r in st.q("""SELECT s.id, s.label, s.walk_mode, COUNT(DISTINCT rd.unit_id) AS n FROM source s
                         LEFT JOIN page p ON p.source_id = s.id LEFT JOIN unit u ON u.page_id = p.id
                         LEFT JOIN round rd ON rd.unit_id = u.id AND rd.complete = 1
                         GROUP BY s.id ORDER BY s.id DESC"""):
            it = QListWidgetItem(f"#{r['id']}  {r['label']}  ({r['walk_mode'] or ''}, {r['n']} read)")
            it.setData(Qt.UserRole, (r["id"], r["label"]))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.list.addItem(it)
        st.close()

    def checked(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def compare(self):
        sel = self.checked()
        if len(sel) < 2:
            self.msg.setText(self.t("pick_two"))
            return
        project = jobs.project_dir()
        st = jobs.open_store(project)
        path = report.write_comparison(st, sel, report.default_out_dir(project, "compare"), self.lang)
        st.close()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def one_report(self):
        sel = self.checked() or ([self.list.currentItem().data(Qt.UserRole)] if self.list.currentItem() else [])
        if not sel:
            return
        project = jobs.project_dir()
        st = jobs.open_store(project)
        sid, label = sel[0]
        path = report.write_source_report(st, sid, report.default_out_dir(project, label), self.lang)
        st.close()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


# --- window ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, session: auth.Session, settings: dict):
        super().__init__()
        self.session, self.settings = session, settings
        self.lang = settings.get("lang", "en")
        self.t = T(self.lang)
        self.setWindowTitle(f"{self.t('app_title')} {__version__}")
        self.resize(980, 820)
        central = QWidget()
        lay = QVBoxLayout(central)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(QLabel(self.t("language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Srpski (latinica)", "sr")
        self.lang_combo.setCurrentIndex(0 if self.lang == "en" else 1)
        self.lang_combo.currentIndexChanged.connect(self.change_lang)
        top.addWidget(self.lang_combo)
        lay.addLayout(top)
        self.tabs = QTabWidget()
        self.model_tab = ModelTab(self.t, session, settings)
        self.read_tab = ReadTab(self.t, settings, self.lang)
        self.manual_tab = ManualTab(self.t, settings)
        self.compare_tab = CompareTab(self.t, self.lang)
        self.tabs.addTab(self.model_tab, self.t("tab_model"))
        self.tabs.addTab(self.read_tab, self.t("tab_read"))
        self.tabs.addTab(self.manual_tab, self.t("tab_manual"))
        self.tabs.addTab(self.compare_tab, self.t("tab_compare"))
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.model_tab.connected.connect(self.on_connected)

    def on_connected(self, conn, spec):
        self.read_tab.set_connection(conn, spec)
        self.manual_tab.conn = conn
        self.tabs.setCurrentWidget(self.read_tab)

    def change_lang(self):
        self.settings["lang"] = self.lang_combo.currentData()
        save_settings(self.settings)
        conn = self.model_tab.conn
        self.model_tab.conn = None  # keep it alive across the rebuild
        w = MainWindow(self.session, self.settings)
        w.show()
        if conn:
            w.model_tab.conn = conn
            w.on_connected(conn, self.read_tab.spec)
            w.tabs.setCurrentIndex(0)
        app = QApplication.instance()
        app._main = w
        self.close()

    def closeEvent(self, e):
        if self.model_tab.conn and QApplication.instance()._main is self:
            self.model_tab.conn.close()
        super().closeEvent(e)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Divide Reader")
    app.setDesktopFileName("divide-reader")
    icon = paths.install_dir() / "divide-reader.svg"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    session = auth.Session()  # logins live only here, until the program closes
    w = MainWindow(session, load_settings())
    app._main = w
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
