from __future__ import annotations

import os
import queue as thread_queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from clips_lives_analyzer.config import load_config
from clips_lives_analyzer.database import QueueDatabase
from clips_lives_analyzer.doctor import run_diagnostics
from clips_lives_analyzer.models import Job, JobStatus
from clips_lives_analyzer.paths import AppPaths
from clips_lives_analyzer.pipeline import AnalyzerPipeline
from clips_lives_analyzer.queue import QueueController
from clips_lives_analyzer.utils import VIDEO_EXTENSIONS


STATUS_LABELS = {
    JobStatus.QUEUED: "Na fila",
    JobStatus.RUNNING: "Analisando",
    JobStatus.PAUSED: "Pausado",
    JobStatus.COMPLETED: "Concluído",
    JobStatus.FAILED: "Falhou",
    JobStatus.CANCELLED: "Cancelado",
}

STAGE_LABELS = {
    "queued": "Aguardando",
    "preflight": "Verificando",
    "probe": "Lendo arquivo",
    "audio": "Preparando áudio",
    "transcribe": "Transcrevendo",
    "signals": "Lendo cenas",
    "proposals": "Buscando candidatos",
    "deep_analysis": "Análise editorial",
    "stories": "Ligando histórias",
    "report": "Salvando timestamps",
    "complete": "Pronto",
}


class AnalyzerWindow:
    def __init__(self, root: tk.Tk, paths: AppPaths):
        self.root = root
        self.paths = paths
        self.config = load_config(paths)
        self.database = QueueDatabase(paths.database)
        self.events: thread_queue.Queue[tuple[str, Job | None]] = thread_queue.Queue()
        self.controller = QueueController(
            self.database,
            AnalyzerPipeline(paths, self.config),
            lambda name, job: self.events.put((name, job)),
        )
        self.root.title("Clips Lives Analyzer")
        self.root.geometry("1120x700")
        self.root.minsize(900, 570)
        self._configure_style()
        self._build()
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=30)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=(18, 16, 18, 8))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Clips Lives Analyzer",
            font=("Segoe UI", 20, "bold"),
        ).pack(side="left")
        ttk.Label(
            header,
            text="Fila local - nenhum VOD sai do computador",
            foreground="#555555",
        ).pack(side="left", padx=18, pady=(8, 0))

        actions = ttk.Frame(self.root, padding=(18, 5))
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="Adicionar VODs",
            command=self._add_files,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(actions, text="Adicionar pasta", command=self._add_folder).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Iniciar fila", command=self.controller.start).pack(
            side="left", padx=(18, 6)
        )
        ttk.Button(
            actions,
            text="Pausar após o atual",
            command=self.controller.pause_after_current,
        ).pack(side="left")
        ttk.Button(actions, text="Configurações", command=self._settings).pack(
            side="right"
        )
        ttk.Button(actions, text="Diagnóstico", command=self._diagnostics).pack(
            side="right", padx=6
        )

        table_frame = ttk.Frame(self.root, padding=(18, 8))
        table_frame.pack(fill="both", expand=True)
        columns = ("file", "status", "stage", "progress")
        self.table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.table.heading("file", text="Arquivo")
        self.table.heading("status", text="Status")
        self.table.heading("stage", text="Etapa")
        self.table.heading("progress", text="Progresso")
        self.table.column("file", width=500, minwidth=260)
        self.table.column("status", width=120, anchor="center")
        self.table.column("stage", width=180, anchor="center")
        self.table.column("progress", width=110, anchor="center")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())
        self.table.bind("<Double-1>", lambda _event: self._open_result())

        selected_actions = ttk.Frame(self.root, padding=(18, 0, 18, 8))
        selected_actions.pack(fill="x")
        ttk.Button(
            selected_actions,
            text="Abrir timestamps",
            command=self._open_result,
        ).pack(side="left")
        ttk.Button(selected_actions, text="Tentar novamente", command=self._retry).pack(
            side="left", padx=6
        )
        ttk.Button(selected_actions, text="Cancelar", command=self._cancel).pack(
            side="left"
        )
        ttk.Button(selected_actions, text="Remover da fila", command=self._remove).pack(
            side="left", padx=6
        )

        details_frame = ttk.LabelFrame(
            self.root,
            text="Resultado do arquivo selecionado",
            padding=10,
        )
        details_frame.pack(fill="x", padx=18, pady=(0, 14))
        self.details = tk.Text(
            details_frame,
            height=7,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.details.pack(fill="x")
        self.footer = ttk.Label(self.root, text="", padding=(18, 0, 18, 10))
        self.footer.pack(fill="x")

    def _selected_job(self) -> Job | None:
        selected = self.table.selection()
        return self.database.get(selected[0]) if selected else None

    def _add_files(self) -> None:
        filenames = filedialog.askopenfilenames(
            title="Selecione um ou mais VODs",
            filetypes=[
                ("Vídeos", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if filenames:
            try:
                self.controller.add_files([Path(name) for name in filenames])
            except Exception as exc:
                messagebox.showerror("Não foi possível adicionar", str(exc))

    def _add_folder(self) -> None:
        directory = filedialog.askdirectory(title="Selecione a pasta de VODs")
        if not directory:
            return
        videos = sorted(
            path
            for path in Path(directory).rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        )
        if not videos:
            messagebox.showinfo("Nenhum VOD", "A pasta não contém vídeos suportados.")
            return
        try:
            self.controller.add_files(videos)
        except Exception as exc:
            messagebox.showerror("Não foi possível adicionar", str(exc))

    def _retry(self) -> None:
        if job := self._selected_job():
            self.database.retry(job.id)
            self.controller.start()

    def _cancel(self) -> None:
        if job := self._selected_job():
            self.controller.cancel(job.id)

    def _remove(self) -> None:
        if job := self._selected_job():
            try:
                self.database.remove(job.id)
            except Exception as exc:
                messagebox.showerror("Não foi possível remover", str(exc))

    def _open_result(self) -> None:
        job = self._selected_job()
        if not job or not job.result_path:
            messagebox.showinfo("Sem resultado", "Este arquivo ainda não possui timestamps.")
            return
        target = Path(job.result_path)
        if not target.exists():
            messagebox.showerror("Arquivo ausente", "O resultado não foi encontrado no disco.")
            return
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _show_selected(self) -> None:
        job = self._selected_job()
        content = ""
        if job:
            if job.result_path and Path(job.result_path).exists():
                content = Path(job.result_path).read_text(encoding="utf-8")
            elif job.error:
                content = f"Falha: {job.error}\n\nO progresso salvo será reaproveitado ao tentar novamente."
            else:
                events = self.database.events(job.id, limit=6)
                content = "\n".join(
                    f"{item['created_at'][11:19]} - {item['message'].splitlines()[0]}"
                    for item in events
                )
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", content)
        self.details.configure(state="disabled")

    def _diagnostics(self) -> None:
        checks = run_diagnostics(self.paths, self.config)
        text = "\n".join(
            f"{'OK' if check.ok else 'ATENÇÃO'} - {check.name}: {check.details}"
            for check in checks
        )
        messagebox.showinfo("Diagnóstico", text)

    def _settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Configurações")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Perfil de análise").grid(row=0, column=0, sticky="w")
        profile = tk.StringVar(value=self.config.analysis_profile)
        ttk.Combobox(
            frame,
            textvariable=profile,
            values=("coverage", "balanced"),
            state="readonly",
            width=20,
        ).grid(row=0, column=1, padx=(14, 0))
        ttk.Label(
            frame,
            text=(
                "coverage: prioriza não perder conteúdo bom\n"
                "balanced: processa menos candidatos"
            ),
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 14))
        cleanup = tk.BooleanVar(value=self.config.cleanup_temporary_files)
        ttk.Checkbutton(
            frame,
            text="Apagar arquivos temporários após concluir",
            variable=cleanup,
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        def save() -> None:
            self.config.analysis_profile = profile.get()
            self.config.cleanup_temporary_files = cleanup.get()
            self.config.save(self.paths.config)
            dialog.destroy()

        ttk.Button(frame, text="Salvar", command=save).grid(
            row=3, column=1, sticky="e", pady=(18, 0)
        )

    def _refresh(self) -> None:
        while True:
            try:
                self.events.get_nowait()
            except thread_queue.Empty:
                break
        jobs = self.database.list()
        existing = set(self.table.get_children())
        current_ids = {job.id for job in jobs}
        for item_id in existing - current_ids:
            self.table.delete(item_id)
        for job in jobs:
            values = (
                job.filename,
                STATUS_LABELS[job.status],
                STAGE_LABELS.get(job.stage.value, job.stage.value),
                f"{job.progress:.0f}%",
            )
            if self.table.exists(job.id):
                self.table.item(job.id, values=values)
            else:
                self.table.insert("", "end", iid=job.id, values=values)
        queued = sum(job.status == JobStatus.QUEUED for job in jobs)
        running = next((job for job in jobs if job.status == JobStatus.RUNNING), None)
        if running:
            text = (
                f"Analisando {running.filename} - {running.progress:.0f}% | "
                f"{queued} arquivo(s) aguardando"
            )
        elif self.controller.paused:
            text = f"Fila pausada | {queued} arquivo(s) aguardando"
        else:
            text = f"{queued} arquivo(s) aguardando"
        self.footer.configure(text=text)
        self._show_selected()
        self.root.after(900, self._refresh)

    def _close(self) -> None:
        running = any(job.status == JobStatus.RUNNING for job in self.database.list())
        if running and not messagebox.askyesno(
            "Fechar",
            "A análise atual será interrompida com segurança e retomada ao abrir novamente. Fechar?",
        ):
            return
        self.controller.shutdown(wait=True)
        self.root.destroy()


def launch(paths: AppPaths | None = None) -> None:
    root = tk.Tk()
    AnalyzerWindow(root, paths or AppPaths.default())
    root.mainloop()
