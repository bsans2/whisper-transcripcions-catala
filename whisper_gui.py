# -*- coding: utf-8 -*-
"""
Whisper · Transcripció d'àudios (interfície gràfica)

Cal executar-lo amb el Python de l'entorn virtual (.venv) on hi ha instal·lat
openai-whisper. Per a això, fes doble clic a "Whisper.bat".
"""

import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

# Amb pythonw.exe (sense consola) stdout i stderr valen None: ho evitem.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

FROZEN = getattr(sys, "frozen", False)  # True quan s'executa com a .exe

# Carpeta del programa: la del .exe, o la del script si s'executa amb Python.
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
CONFIG_FILE = BASE / "whisper_gui_config.json"
MODELS_DIR = BASE / "models"  # opcional: models .pt per no haver de descarregar-los


def resource_path(name: str) -> Path:
    """Ruta d'un fitxer inclòs dins del programa (p. ex. la icona)."""
    return Path(getattr(sys, "_MEIPASS", BASE)) / name


# Si hi ha un ffmpeg.exe al costat del programa, Whisper el trobarà sol.
os.environ["PATH"] = str(BASE) + os.pathsep + os.environ.get("PATH", "")

# A Windows, evita que es vegi una finestra negra cada cop que Whisper crida ffmpeg.
if os.name == "nt":
    _popen_init = subprocess.Popen.__init__

    def _popen_sense_finestra(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000  # CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_sense_finestra

AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".flac", ".aac",
    ".wma", ".mp4", ".mkv", ".webm", ".mov", ".avi", ".amr",
}

LANGS = {
    "Català": "ca",
    "Castellà": "es",
    "Anglès": "en",
    "Francès": "fr",
    "Detectar automàticament": None,
}

MODEL_HINTS = {
    "tiny": "molt ràpid, precisió limitada",
    "base": "ràpid, precisió bàsica",
    "small": "equilibrat (recomanat per començar)",
    "medium": "més lent, més precís",
    "large": "el més lent i el més precís; necessita molta memòria",
}

FORMATS = ["txt", "srt", "vtt", "json", "tsv", "tots"]
FORMAT_HINTS = {
    "txt": "text pla",
    "srt": "subtítols amb temps",
    "vtt": "subtítols WebVTT",
    "json": "dades estructurades",
    "tsv": "dades separades per tabuladors",
    "tots": "genera tots els formats",
}
FORMAT_EXTS = {
    "txt": ["txt"], "srt": ["srt"], "vtt": ["vtt"], "json": ["json"],
    "tsv": ["tsv"], "tots": ["txt", "srt", "vtt", "json", "tsv"],
}


class Cancelled(Exception):
    """S'ha premut «Aturar»."""


# ---------------------------------------------------------------------------
# Funcions auxiliars (sense interfície)
# ---------------------------------------------------------------------------

def clean_filename(name: str) -> str:
    """Treu els caràcters que Windows no permet en un nom de fitxer."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().strip(".")
    return name


def unique_stem(out_dir: Path, stem: str, fmt: str) -> str:
    """Retorna un nom que no sobreescrigui cap fitxer existent."""
    exts = FORMAT_EXTS[fmt]
    candidate, n = stem, 2
    while any((out_dir / f"{candidate}.{e}").exists() for e in exts):
        candidate = f"{stem} ({n})"
        n += 1
    return candidate


def format_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} h {m} min {s} s"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


def transcribe_worker(files, out_dir, custom_name, lang_code, model_name,
                      fmt, q, cancel):
    """Transcriu els fitxers. S'executa en un fil a part i parla amb la
    interfície a través de la cua q."""
    ok, errors = 0, 0
    try:
        q.put(("log", "Carregant Whisper (pot trigar una mica)…"))
        import torch
        import tqdm
        from tqdm.std import tqdm as BaseTqdm
        import whisper
        from whisper.utils import get_writer

        class ProgressTqdm(BaseTqdm):
            """Substitueix la barra de progrés de Whisper per la nostra."""

            def __init__(self, *args, **kwargs):
                kwargs["file"] = io.StringIO()
                super().__init__(*args, **kwargs)

            def update(self, n=1):
                result = super().update(n)
                if cancel.is_set():
                    raise Cancelled()
                if self.total:
                    q.put(("progress", min(self.n / self.total, 1.0)))
                return result

        use_fp16 = torch.cuda.is_available()
        q.put(("log", f"Carregant el model «{model_name}» "
                      "(si és la primera vegada, es descarrega)…"))
        model = whisper.load_model(
            model_name,
            download_root=str(MODELS_DIR) if MODELS_DIR.is_dir() else None)
        if cancel.is_set():
            raise Cancelled()

        writer = get_writer("all" if fmt == "tots" else fmt, str(out_dir))
        writer_options = {"highlight_words": False,
                          "max_line_count": None,
                          "max_line_width": None}

        original_tqdm = tqdm.tqdm
        tqdm.tqdm = ProgressTqdm
        try:
            total = len(files)
            for i, path in enumerate(files, 1):
                if cancel.is_set():
                    raise Cancelled()
                q.put(("file_start", i, total, path.name))
                t0 = time.time()
                try:
                    result = model.transcribe(
                        str(path), language=lang_code,
                        fp16=use_fp16, verbose=False)

                    if custom_name and total == 1:
                        stem = clean_filename(custom_name)
                    else:
                        stem = ""
                    stem = stem or clean_filename(path.stem) or "transcripcio"
                    stem = unique_stem(out_dir, stem, fmt)

                    # Whisper només fa servir el nom base per posar el nom
                    # al fitxer de sortida; així podem triar-lo nosaltres.
                    writer(result, stem + ".audio", writer_options)

                    ok += 1
                    q.put(("file_done", i, total,
                           f"✔ {path.name} → {stem}.{FORMAT_EXTS[fmt][0]}"
                           f"{' (i altres formats)' if fmt == 'tots' else ''}"
                           f"  [{format_seconds(time.time() - t0)}]"))
                except Cancelled:
                    raise
                except Exception as e:  # error en un fitxer concret
                    errors += 1
                    msg = f"✖ {path.name}: {e}"
                    if "ffmpeg" in str(e).lower():
                        msg += ("\n   (Sembla que FFmpeg no és accessible. "
                                "Comprova que la carpeta bin de FFmpeg és al PATH.)")
                    q.put(("file_error", i, total, msg))
        finally:
            tqdm.tqdm = original_tqdm

        q.put(("finished", ok, errors, False))
    except Cancelled:
        q.put(("finished", ok, errors, True))
    except Exception as e:
        q.put(("fatal", f"{type(e).__name__}: {e}"))


# ---------------------------------------------------------------------------
# Interfície
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Whisper · Transcripció d'àudios")
        self.geometry("800x780")
        self.minsize(700, 680)
        try:
            self.iconbitmap(str(resource_path("icona_whisper.ico")))
        except Exception:
            pass  # si no hi ha icona, es queda la per defecte

        self.files: list[Path] = []
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.thread = None
        self.running = False
        self.last_audio_dir = BASE / "audios"

        cfg = self.load_config()
        default_out = cfg.get("out_dir") or str(BASE / "transcripcions")
        self.out_dir = tk.StringVar(value=default_out)
        self.name_var = tk.StringVar()
        lang = cfg.get("lang", "Català")
        self.lang_var = tk.StringVar(value=lang if lang in LANGS else "Català")
        model = cfg.get("model", "small")
        self.model_var = tk.StringVar(value=model if model in MODEL_HINTS else "small")
        fmt = cfg.get("fmt", "txt")
        self.fmt_var = tk.StringVar(value=fmt if fmt in FORMATS else "txt")

        self.setup_style()
        self.build_ui()
        self.update_controls()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll_queue)

    # -- configuració -------------------------------------------------------

    def load_config(self) -> dict:
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_config(self):
        try:
            CONFIG_FILE.write_text(json.dumps({
                "out_dir": self.out_dir.get(),
                "lang": self.lang_var.get(),
                "model": self.model_var.get(),
                "fmt": self.fmt_var.get(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- aspecte ------------------------------------------------------------

    def setup_style(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # text més nítid
        except Exception:
            pass
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except Exception:
                pass
        style = ttk.Style(self)
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))
        style.configure("Hint.TLabel", foreground="#666666")

    def build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)

        # 1. Àudios ---------------------------------------------------------
        f1 = ttk.LabelFrame(root, text=" 1. Àudios a transcriure ", padding=10)
        f1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        f1.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(f1, height=6, selectmode="extended",
                                  activestyle="none")
        sb = ttk.Scrollbar(f1, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.grid(row=0, column=0, rowspan=4, sticky="nsew")
        sb.grid(row=0, column=1, rowspan=4, sticky="ns")

        self.btn_add = ttk.Button(f1, text="Afegir àudios…", command=self.add_files)
        self.btn_folder = ttk.Button(f1, text="Afegir carpeta…", command=self.add_folder)
        self.btn_remove = ttk.Button(f1, text="Treure seleccionats", command=self.remove_selected)
        self.btn_clear = ttk.Button(f1, text="Buidar llista", command=self.clear_files)
        for r, b in enumerate((self.btn_add, self.btn_folder, self.btn_remove, self.btn_clear)):
            b.grid(row=r, column=2, sticky="ew", padx=(10, 0), pady=2)

        # 2. Carpeta de sortida ---------------------------------------------
        f2 = ttk.LabelFrame(root, text=" 2. On es desaran les transcripcions ", padding=10)
        f2.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        f2.columnconfigure(0, weight=1)
        self.out_entry = ttk.Entry(f2, textvariable=self.out_dir)
        self.out_entry.grid(row=0, column=0, sticky="ew")
        self.btn_out = ttk.Button(f2, text="Canvia…", command=self.choose_out_dir)
        self.btn_out.grid(row=0, column=1, padx=(10, 0))
        self.btn_open = ttk.Button(f2, text="Obre la carpeta", command=self.open_out_dir)
        self.btn_open.grid(row=0, column=2, padx=(6, 0))

        # 3. Opcions --------------------------------------------------------
        f3 = ttk.LabelFrame(root, text=" 3. Opcions ", padding=10)
        f3.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        f3.columnconfigure(1, weight=1)

        ttk.Label(f3, text="Nom del fitxer:").grid(row=0, column=0, sticky="w", pady=3)
        self.name_entry = ttk.Entry(f3, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=3)
        self.name_hint = ttk.Label(f3, text="", style="Hint.TLabel")
        self.name_hint.grid(row=0, column=2, sticky="w")

        ttk.Label(f3, text="Idioma:").grid(row=1, column=0, sticky="w", pady=3)
        self.lang_cb = ttk.Combobox(f3, textvariable=self.lang_var, state="readonly",
                                    values=list(LANGS.keys()), width=24)
        self.lang_cb.grid(row=1, column=1, sticky="w", padx=8, pady=3)

        ttk.Label(f3, text="Model:").grid(row=2, column=0, sticky="w", pady=3)
        self.model_cb = ttk.Combobox(f3, textvariable=self.model_var, state="readonly",
                                     values=list(MODEL_HINTS.keys()), width=24)
        self.model_cb.grid(row=2, column=1, sticky="w", padx=8, pady=3)
        self.model_hint = ttk.Label(f3, text="", style="Hint.TLabel")
        self.model_hint.grid(row=2, column=2, sticky="w")

        ttk.Label(f3, text="Format de sortida:").grid(row=3, column=0, sticky="w", pady=3)
        self.fmt_cb = ttk.Combobox(f3, textvariable=self.fmt_var, state="readonly",
                                   values=FORMATS, width=24)
        self.fmt_cb.grid(row=3, column=1, sticky="w", padx=8, pady=3)
        self.fmt_hint = ttk.Label(f3, text="", style="Hint.TLabel")
        self.fmt_hint.grid(row=3, column=2, sticky="w")

        self.model_cb.bind("<<ComboboxSelected>>", lambda e: self.update_hints())
        self.fmt_cb.bind("<<ComboboxSelected>>", lambda e: self.update_hints())
        self.update_hints()

        # Botons d'acció -----------------------------------------------------
        f4 = ttk.Frame(root)
        f4.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.btn_start = ttk.Button(f4, text="▶  Transcriure", style="Big.TButton",
                                    command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(f4, text="■  Aturar", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=10)

        # Progrés ------------------------------------------------------------
        f5 = ttk.Frame(root)
        f5.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        f5.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Afegeix un o més àudios per començar.")
        ttk.Label(f5, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.pct_var = tk.StringVar(value="")
        ttk.Label(f5, textvariable=self.pct_var).grid(row=0, column=1, sticky="e")
        self.pbar = ttk.Progressbar(f5, mode="determinate", maximum=100)
        self.pbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Registre -----------------------------------------------------------
        f6 = ttk.LabelFrame(root, text=" Registre ", padding=6)
        f6.grid(row=5, column=0, sticky="nsew")
        f6.columnconfigure(0, weight=1)
        f6.rowconfigure(0, weight=1)
        self.log = tk.Text(f6, height=8, wrap="word", state="disabled",
                           font=("Consolas", 9), relief="flat")
        lsb = ttk.Scrollbar(f6, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        lsb.grid(row=0, column=1, sticky="ns")

        self.lockable = [self.btn_add, self.btn_folder, self.btn_remove, self.btn_clear,
                         self.btn_out, self.out_entry, self.lang_cb, self.model_cb,
                         self.fmt_cb, self.listbox]

    # -- utilitats d'interfície ---------------------------------------------

    def update_hints(self):
        self.model_hint.configure(text=MODEL_HINTS.get(self.model_var.get(), ""))
        self.fmt_hint.configure(text=FORMAT_HINTS.get(self.fmt_var.get(), ""))

    def update_controls(self):
        """Activa o desactiva el camp del nom segons el nombre d'àudios."""
        if self.running:
            self.name_entry.configure(state="disabled")
            return
        if len(self.files) == 1:
            self.name_entry.configure(state="normal")
            self.name_hint.configure(text="(buit = mateix nom que l'àudio)")
        else:
            self.name_entry.configure(state="disabled")
            self.name_hint.configure(
                text="(només amb un àudio; si no, es fa servir el nom de cada àudio)")
        n = len(self.files)
        if not self.running:
            self.status_var.set(
                "Afegeix un o més àudios per començar." if n == 0
                else f"{n} àudio{'s' if n != 1 else ''} a la llista.")

    def write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for p in self.files:
            self.listbox.insert("end", p.name)
        self.update_controls()

    def set_running(self, running: bool):
        self.running = running
        state = "disabled" if running else "normal"
        for w in self.lockable:
            try:
                w.configure(state=state)
            except tk.TclError:
                pass
        for cb in (self.lang_cb, self.model_cb, self.fmt_cb):
            cb.configure(state="disabled" if running else "readonly")
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.update_controls()

    def set_indeterminate(self):
        self.pbar.stop()
        self.pbar.configure(mode="indeterminate")
        self.pbar.start(12)
        self.pct_var.set("")

    def set_determinate(self, value=0.0):
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar["value"] = value

    # -- gestió de la llista d'àudios ----------------------------------------

    def _add_paths(self, paths):
        existing = {p.resolve() for p in self.files}
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.resolve() not in existing:
                self.files.append(p)
                existing.add(p.resolve())
                added += 1
        self.refresh_list()
        return added

    def add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXT))
        initial = self.last_audio_dir if self.last_audio_dir.exists() else BASE
        paths = filedialog.askopenfilenames(
            title="Selecciona els àudios", initialdir=str(initial),
            filetypes=[("Àudio i vídeo", exts), ("Tots els fitxers", "*.*")])
        if paths:
            self.last_audio_dir = Path(paths[0]).parent
            self._add_paths(paths)

    def add_folder(self):
        initial = self.last_audio_dir if self.last_audio_dir.exists() else BASE
        folder = filedialog.askdirectory(title="Selecciona una carpeta amb àudios",
                                         initialdir=str(initial))
        if not folder:
            return
        self.last_audio_dir = Path(folder)
        found = sorted(p for p in Path(folder).iterdir()
                       if p.is_file() and p.suffix.lower() in AUDIO_EXT)
        if not found:
            messagebox.showinfo("Cap àudio trobat",
                                "No s'ha trobat cap fitxer d'àudio en aquesta carpeta.")
            return
        self._add_paths(found)

    def remove_selected(self):
        for idx in sorted(self.listbox.curselection(), reverse=True):
            del self.files[idx]
        self.refresh_list()

    def clear_files(self):
        self.files.clear()
        self.refresh_list()

    # -- carpeta de sortida --------------------------------------------------

    def choose_out_dir(self):
        current = Path(self.out_dir.get())
        folder = filedialog.askdirectory(
            title="Carpeta on desar les transcripcions",
            initialdir=str(current if current.exists() else BASE))
        if folder:
            self.out_dir.set(str(Path(folder)))

    def open_out_dir(self):
        folder = Path(self.out_dir.get())
        if not folder.exists():
            messagebox.showinfo("Carpeta inexistent",
                                "Aquesta carpeta encara no existeix. "
                                "Es crearà quan facis la primera transcripció.")
            return
        try:
            os.startfile(str(folder))  # només Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", str(folder)])

    # -- transcripció --------------------------------------------------------

    def start(self):
        if not self.files:
            messagebox.showwarning("Falten àudios", "Afegeix almenys un àudio a la llista.")
            return
        missing = [p.name for p in self.files if not p.exists()]
        if missing:
            messagebox.showerror("Fitxer no trobat",
                                 "Aquests fitxers ja no existeixen:\n\n" + "\n".join(missing))
            return
        out_dir = Path(self.out_dir.get().strip() or str(BASE / "transcripcions"))
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Carpeta de sortida", f"No es pot crear la carpeta:\n{e}")
            return

        self.save_config()
        self.cancel.clear()
        self.set_running(True)
        self.set_indeterminate()
        self.status_var.set("Preparant…")
        self.write_log("─" * 60)
        self.write_log(f"Model: {self.model_var.get()} · Idioma: {self.lang_var.get()} "
                       f"· Format: {self.fmt_var.get()}")

        self.thread = threading.Thread(
            target=transcribe_worker, daemon=True,
            args=(list(self.files), out_dir, self.name_var.get().strip(),
                  LANGS[self.lang_var.get()], self.model_var.get(),
                  self.fmt_var.get(), self.q, self.cancel))
        self.thread.start()

    def stop(self):
        if self.running:
            self.cancel.set()
            self.btn_stop.configure(state="disabled")
            self.status_var.set("Aturant… (acabarà d'aquí un moment)")

    def poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.write_log(msg[1])
                elif kind == "file_start":
                    _, i, total, name = msg
                    self.status_var.set(f"Àudio {i} de {total}: {name}")
                    self.write_log(f"Transcrivint {name}…")
                    self.set_indeterminate()
                elif kind == "progress":
                    if str(self.pbar.cget("mode")) != "determinate":
                        self.set_determinate()
                    self.pbar["value"] = msg[1] * 100
                    self.pct_var.set(f"{int(msg[1] * 100)} %")
                elif kind == "file_done":
                    self.set_determinate(100)
                    self.pct_var.set("100 %")
                    self.write_log(msg[3])
                elif kind == "file_error":
                    self.write_log(msg[3])
                elif kind == "fatal":
                    self.set_running(False)
                    self.set_determinate(0)
                    self.pct_var.set("")
                    self.status_var.set("S'ha produït un error.")
                    self.write_log("✖ Error: " + msg[1])
                    consell = ("Comprova que la carpeta del programa està sencera "
                               "(no moguis Whisper.exe fora de la seva carpeta)."
                               if FROZEN else
                               "Comprova que aquest programa s'ha obert amb Whisper.bat "
                               "(entorn virtual .venv).")
                    messagebox.showerror(
                        "Error",
                        "No s'ha pogut fer la transcripció:\n\n" + msg[1] +
                        "\n\n" + consell)
                elif kind == "finished":
                    _, ok, errors, cancelled = msg
                    self.set_running(False)
                    self.set_determinate(0 if cancelled else 100)
                    self.pct_var.set("")
                    if cancelled:
                        self.status_var.set("Aturat.")
                        self.write_log("■ Procés aturat.")
                    else:
                        resum = f"Fet: {ok} transcripció(ns) correcta(es)"
                        if errors:
                            resum += f", {errors} amb errors"
                        self.status_var.set(resum + ".")
                        self.write_log(resum + ".")
                        if ok and messagebox.askyesno(
                                "Transcripció acabada",
                                f"{resum}.\n\nVols obrir la carpeta amb els resultats?"):
                            self.open_out_dir()
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def on_close(self):
        if self.running and not messagebox.askyesno(
                "Sortir", "Hi ha una transcripció en curs. Segur que vols sortir?"):
            return
        self.cancel.set()
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
