from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from live_splitter.media import require_tools
from live_splitter.models import SplitResult
from live_splitter.runtime import configure_logging
from live_splitter.splitter import VodSplitter
from live_splitter.transcription import (
    FasterWhisperTranscriber,
    transcribe_split_result,
    update_manifest_transcription,
)
from live_splitter.utils import VIDEO_EXTENSIONS, ProcessCancelled, run_process

LOGGER = logging.getLogger(__name__)


def _self_test_transcription(ffmpeg: str) -> None:
    with tempfile.TemporaryDirectory() as temp:
        audio = Path(temp) / "teste.wav"
        run_process(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=16000:duration=1",
                "-y",
                str(audio),
            ],
            timeout_seconds=30,
        )
        FasterWhisperTranscriber(model_name="tiny").transcribe(
            audio,
            duration=1.0,
        )


@dataclass
class QueueItem:
    source: Path
    status: str = "Na fila"
    progress: float = 0.0
    message: str = "Aguardando"
    result: SplitResult | None = None
    error: str | None = None
    warning: str | None = None


class SplitterWindow:
    def __init__(self, root: tk.Tk, log_path: Path):
        self.root = root
        self.log_path = log_path
        self.items: list[QueueItem] = []
        self.events: queue.Queue[tuple[str, int, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.output_root = tk.StringVar(
            value=str(Path.home() / "Videos" / "Lives picotadas")
        )
        self.generate_transcription = tk.BooleanVar(value=True)
        self.root.title("Picotador de Lives")
        self.root.geometry("1050x650")
        self.root.minsize(840, 520)
        self._build()
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=(18, 16, 18, 8))
        header.pack(fill="x")
        ttk.Label(
            header, text="Picotador de Lives", font=("Segoe UI", 20, "bold")
        ).pack(side="left")
        ttk.Label(
            header,
            text="Sem compressão - <256 MB - até 20 min - transcrição PT-BR",
            foreground="#555555",
        ).pack(side="left", padx=18, pady=(8, 0))

        output = ttk.Frame(self.root, padding=(18, 6))
        output.pack(fill="x")
        ttk.Label(output, text="Pasta de saída:").pack(side="left")
        ttk.Entry(output, textvariable=self.output_root).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(output, text="Escolher", command=self._choose_output).pack(
            side="left"
        )

        actions = ttk.Frame(self.root, padding=(18, 6))
        actions.pack(fill="x")
        ttk.Button(actions, text="Adicionar lives", command=self._add_files).pack(
            side="left"
        )
        ttk.Button(
            actions, text="Remover selecionada", command=self._remove_selected
        ).pack(side="left", padx=6)
        ttk.Button(actions, text="Iniciar fila", command=self._start).pack(
            side="left", padx=(18, 6)
        )
        ttk.Button(actions, text="Cancelar atual", command=self.cancel_event.set).pack(
            side="left"
        )
        ttk.Checkbutton(
            actions,
            text="Transcrever em português (large-v3)",
            variable=self.generate_transcription,
        ).pack(side="left", padx=(18, 0))
        ttk.Button(actions, text="Abrir resultado", command=self._open_result).pack(
            side="right"
        )
        ttk.Button(actions, text="Abrir log", command=self._open_log).pack(
            side="right", padx=6
        )

        table_frame = ttk.Frame(self.root, padding=(18, 8))
        table_frame.pack(fill="both", expand=True)
        columns = ("file", "status", "progress", "message")
        self.table = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        for column, label in zip(
            columns,
            ("Live", "Status", "Progresso", "Etapa"),
            strict=True,
        ):
            self.table.heading(column, text=label)
        self.table.column("file", width=390, minwidth=220)
        self.table.column("status", width=110, anchor="center")
        self.table.column("progress", width=90, anchor="center")
        self.table.column("message", width=360, minwidth=220)
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.footer = ttk.Label(
            self.root, padding=(18, 4, 18, 14), foreground="#555555"
        )
        self.footer.pack(fill="x")

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(
            title="Escolha onde salvar as lives picotadas"
        )
        if selected:
            self.output_root.set(selected)

    def _add_files(self) -> None:
        patterns = " ".join(f"*{item}" for item in sorted(VIDEO_EXTENSIONS))
        selected = filedialog.askopenfilenames(
            title="Selecione uma ou mais lives",
            filetypes=[("Vídeos", patterns), ("Todos os arquivos", "*.*")],
        )
        existing = {item.source.resolve() for item in self.items}
        for raw in selected:
            path = Path(raw)
            if path.resolve() not in existing:
                self.items.append(QueueItem(path))
                existing.add(path.resolve())

    def _selected_index(self) -> int | None:
        selected = self.table.selection()
        return int(selected[0]) if selected else None

    def _remove_selected(self) -> None:
        index = self._selected_index()
        if index is None or self.worker and self.worker.is_alive():
            return
        self.items.pop(index)
        self._rebuild_table()

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        generate_transcription = self.generate_transcription.get()
        pending = [
            index
            for index, item in enumerate(self.items)
            if item.status in {"Na fila", "Falhou", "Cancelado"}
            or (generate_transcription and item.status == "Concluído com aviso")
        ]
        if not pending:
            messagebox.showinfo("Fila vazia", "Adicione ao menos uma live.")
            return
        output = Path(self.output_root.get()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Pasta inválida", str(exc))
            return
        self.cancel_event.clear()
        self.worker = threading.Thread(
            target=self._run_queue,
            args=(pending, output, generate_transcription),
            daemon=True,
        )
        self.worker.start()

    def _run_queue(
        self,
        pending: list[int],
        output: Path,
        generate_transcription: bool,
    ) -> None:
        splitter = VodSplitter()
        for index in pending:
            if self.cancel_event.is_set():
                break
            try:
                result = (
                    self.items[index].result
                    if generate_transcription
                    and self.items[index].result is not None
                    and self.items[index].status
                    in {"Concluído com aviso", "Cancelado"}
                    else None
                )
                if result is None:
                    self.events.put(
                        ("status", index, ("Picotando", 0.0, "Iniciando"))
                    )
                    result = splitter.split(
                        self.items[index].source,
                        output,
                        progress=lambda ratio, message, item_index=index: self.events.put(
                            (
                                "progress",
                                item_index,
                                (
                                    ratio * (0.65 if generate_transcription else 1.0),
                                    message,
                                ),
                            )
                        ),
                        cancelled=self.cancel_event.is_set,
                    )
                    self.events.put(("partial_result", index, result))
                else:
                    self.events.put(
                        (
                            "status",
                            index,
                            ("Transcrevendo", 65.0, "Tentando novamente sem refazer cortes"),
                        )
                    )
                if generate_transcription:
                    self.events.put(
                        (
                            "status",
                            index,
                            ("Transcrevendo", 65.0, "Preparando faster-whisper"),
                        )
                    )
                    try:
                        transcribe_split_result(
                            result,
                            progress=lambda ratio, message, item_index=index: self.events.put(
                                (
                                    "progress",
                                    item_index,
                                    (0.65 + ratio * 0.35, message),
                                )
                            ),
                            cancelled=self.cancel_event.is_set,
                        )
                    except ProcessCancelled:
                        update_manifest_transcription(
                            result,
                            error="Transcrição cancelada pelo usuário",
                        )
                        raise
                    except Exception as exc:
                        LOGGER.exception(
                            "Partes prontas, mas a transcrição falhou para %s",
                            self.items[index].source,
                        )
                        warning = f"{type(exc).__name__}: {exc}"
                        update_manifest_transcription(result, error=warning)
                        self.events.put(("done_warning", index, (result, warning)))
                        continue
                self.events.put(
                    ("done", index, (result, generate_transcription))
                )
            except ProcessCancelled:
                LOGGER.info("Processamento cancelado: %s", self.items[index].source)
                self.events.put(("cancelled", index, None))
                break
            except Exception as exc:
                LOGGER.exception("Falha ao picotar %s", self.items[index].source)
                self.events.put(("error", index, f"{type(exc).__name__}: {exc}"))
        self.events.put(("queue_finished", -1, None))

    @staticmethod
    def _open_path(target: Path) -> None:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _open_result(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Sem seleção", "Selecione uma live na fila.")
            return
        item = self.items[index]
        if item.error:
            messagebox.showerror("Falha ao picotar", item.error)
            return
        if item.warning:
            messagebox.showwarning(
                "Vídeos prontos; transcrição incompleta",
                f"Os vídeos e manifestos foram gerados normalmente.\n\n{item.warning}",
            )
        if not item.result:
            messagebox.showinfo(
                "Sem resultado", "A live selecionada ainda não foi concluída."
            )
            return
        self._open_path(item.result.output_dir)

    def _open_log(self) -> None:
        self._open_path(self.log_path)

    def _rebuild_table(self) -> None:
        for item_id in self.table.get_children():
            self.table.delete(item_id)
        for index, item in enumerate(self.items):
            self.table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.source.name,
                    item.status,
                    f"{item.progress:.0f}%",
                    item.message,
                ),
            )

    def _refresh(self) -> None:
        changed = False
        while True:
            try:
                event, index, payload = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if event == "status":
                status, progress, message = payload  # type: ignore[misc]
                self.items[index].status = status
                self.items[index].progress = progress
                self.items[index].message = message
                if status == "Picotando":
                    self.items[index].error = None
                    self.items[index].warning = None
            elif event == "progress":
                ratio, message = payload  # type: ignore[misc]
                self.items[index].progress = float(ratio) * 100
                self.items[index].message = str(message)
            elif event == "done":
                result, has_transcription = payload  # type: ignore[misc]
                self.items[index].status = "Concluído"
                self.items[index].progress = 100
                self.items[index].message = (
                    "Partes, manifesto e transcrição prontos"
                    if has_transcription
                    else "Partes e manifesto prontos"
                )
                self.items[index].result = result
                self.items[index].warning = None
                self.items[index].error = None
            elif event == "partial_result":
                self.items[index].result = payload  # type: ignore[assignment]
            elif event == "done_warning":
                result, warning = payload  # type: ignore[misc]
                self.items[index].status = "Concluído com aviso"
                self.items[index].progress = 100
                self.items[index].message = "Partes prontas; transcrição falhou"
                self.items[index].result = result
                self.items[index].warning = str(warning)
                self.items[index].error = None
            elif event == "cancelled":
                self.items[index].status = "Cancelado"
                self.items[index].message = "Interrompido pelo usuário"
            elif event == "error":
                self.items[index].status = "Falhou"
                self.items[index].error = str(payload)
                self.items[index].message = str(payload).splitlines()[0]
            elif event == "queue_finished":
                self.cancel_event.clear()
        if changed or len(self.table.get_children()) != len(self.items):
            self._rebuild_table()
        completed = sum(item.status.startswith("Concluído") for item in self.items)
        self.footer.configure(
            text=(
                f"{len(self.items)} live(s) na fila - {completed} concluída(s). "
                "O original nunca é alterado."
            )
        )
        self.root.after(500, self._refresh)

    def _close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(
                "Fechar",
                "O corte atual será interrompido. Os arquivos já concluídos permanecem. Fechar?",
            ):
                return
            self.cancel_event.set()
            self.worker.join(timeout=8)
        self.root.destroy()


def main() -> None:
    log_path = configure_logging()
    LOGGER.info("Iniciando Picotador de Lives")
    self_test = "--self-test" in sys.argv
    try:
        ffmpeg, ffprobe = require_tools()
        if self_test:
            run_process([ffmpeg, "-version"], timeout_seconds=30)
            run_process([ffprobe, "-version"], timeout_seconds=30)
            version = FasterWhisperTranscriber.require_runtime()
            LOGGER.info("faster-whisper %s encontrado", version)
            _self_test_transcription(ffmpeg)
            LOGGER.info("Autoteste concluído com sucesso")
            return
        root = tk.Tk()
        SplitterWindow(root, log_path)
        root.mainloop()
    except Exception as exc:
        LOGGER.exception("Falha fatal ao iniciar o programa")
        if self_test:
            raise
        try:
            messagebox.showerror(
                "Picotador de Lives",
                f"O programa não conseguiu iniciar.\n\n{exc}\n\nLog: {log_path}",
            )
        except tk.TclError:
            pass
        raise
