from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Any
from tkinter import messagebox, scrolledtext, ttk

try:
    from local_engine_windows.daemon import DEFAULT_HOST, DEFAULT_PORT, EngineRuntime, create_app
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution
    from daemon import DEFAULT_HOST, DEFAULT_PORT, EngineRuntime, create_app


class LocalEngineWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Studio Voice Local Engine")
        self.root.geometry("920x640")
        self.root.minsize(760, 560)

        self.colors = {
            "bg": "#0B1324",
            "card": "#141F37",
            "card_alt": "#1A2743",
            "text": "#E8F0FF",
            "muted": "#92A0BD",
            "accent": "#2CC4A8",
            "accent_hover": "#22A88F",
            "danger": "#F07178",
            "warning": "#F4B860",
            "log_bg": "#0A1020",
            "border": "#223152",
        }
        self.root.configure(bg=self.colors["bg"])

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.data_dir = Path(os.getenv("LOCAL_ENGINE_DATA_DIR", Path.home() / ".studio_voice_local"))
        self.logs_dir = self.data_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_file_path = self.logs_dir / f"launcher-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
        self.runtime = EngineRuntime(logger=self.enqueue_log)
        self.api_app = create_app(self.runtime)

        self.server: Any | None = None
        self.server_thread: threading.Thread | None = None
        self.is_running = False

        self.status_var = tk.StringVar(value="Detenido")
        self.status_chip_var = tk.StringVar(value="OFFLINE")
        self.server_url_var = tk.StringVar(value=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
        self.token_var = tk.StringVar(value=self.runtime.api_token)
        self.backend_var = tk.StringVar(value=self._resolve_backend_text())

        self._configure_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.handle_close)
        self.start_server()
        self.root.after(150, self.flush_logs)

    def _resolve_backend_text(self) -> str:
        runtime_class = getattr(self.runtime, "_runtime_class", lambda: self.runtime.inference_backend)()
        quality_tier = getattr(self.runtime, "_quality_tier", lambda: "unknown")()
        backend_text = f"{runtime_class} / {quality_tier}"
        if self.runtime.inference_backend == "chatterbox":
            reason = getattr(self.runtime, "real_backend_device_reason", "") or "n/a"
            backend_text = f"{runtime_class} -> chatterbox ({self.runtime.real_backend_device}, reason={reason})"
        if self.runtime.inference_backend == "mock" and self.runtime.real_backend_error:
            backend_text = f"{runtime_class} -> mock ({self.runtime.real_backend_error})"
        return backend_text

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card"], relief=tk.FLAT)
        style.configure("CardAlt.TFrame", background=self.colors["card_alt"], relief=tk.FLAT)

        style.configure(
            "Title.TLabel",
            background=self.colors["card"],
            foreground=self.colors["text"],
            font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.colors["card"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=self.colors["card"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "SectionAlt.TLabel",
            background=self.colors["card_alt"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "StatusChip.TLabel",
            background=self.colors["card"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "StatusText.TLabel",
            background=self.colors["card"],
            foreground=self.colors["text"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "BackendValue.TLabel",
            background=self.colors["card_alt"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=self.colors["card"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Primary.TButton",
            background=self.colors["accent"],
            foreground="#061722",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            focusthickness=2,
            focuscolor=self.colors["accent"],
            padding=(14, 8),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("pressed", self.colors["accent_hover"]),
                ("active", self.colors["accent_hover"]),
                ("disabled", "#4E6770"),
            ],
            foreground=[("disabled", "#9FB4BB")],
        )
        style.configure(
            "Danger.TButton",
            background=self.colors["danger"],
            foreground="#23090E",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            padding=(14, 8),
        )
        style.map(
            "Danger.TButton",
            background=[
                ("pressed", "#DB5F66"),
                ("active", "#DB5F66"),
                ("disabled", "#5F3B43"),
            ],
            foreground=[("disabled", "#BC9AA0")],
        )
        style.configure(
            "Secondary.TButton",
            background=self.colors["card_alt"],
            foreground=self.colors["text"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
            padding=(10, 7),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("pressed", "#213259"),
                ("active", "#213259"),
                ("disabled", "#2D3954"),
            ],
            foreground=[("disabled", "#7F8BA6")],
        )

        style.configure(
            "ReadOnly.TEntry",
            fieldbackground="#0E172C",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            insertcolor=self.colors["text"],
            padding=(8, 7),
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, style="App.TFrame", padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        hero = ttk.Frame(container, style="Card.TFrame", padding=(22, 18))
        hero.pack(fill=tk.X)

        title = ttk.Label(
            hero,
            text="Modo Pro Local Engine",
            style="Title.TLabel",
            anchor="w",
            justify=tk.LEFT,
        )
        title.pack(fill=tk.X, pady=(0, 6))

        subtitle = ttk.Label(
            hero,
            text=(
                "Esta app corre en localhost para ejecutar la ruta real de Chatterbox fuera del navegador.\n"
                "Codigo abierto y auditable. Al cerrar esta ventana, se apaga el daemon local."
            ),
            style="Subtitle.TLabel",
            justify=tk.LEFT,
            anchor="w",
            wraplength=780,
        )
        subtitle.pack(fill=tk.X)

        summary_row = ttk.Frame(container, style="App.TFrame")
        summary_row.pack(fill=tk.X, pady=(12, 0))

        status_card = ttk.Frame(summary_row, style="Card.TFrame", padding=(16, 14))
        status_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(status_card, text="ESTADO", style="Section.TLabel").pack(anchor="w")
        status_line = ttk.Frame(status_card, style="Card.TFrame")
        status_line.pack(anchor="w", pady=(8, 0))

        self.status_dot = tk.Canvas(
            status_line,
            width=14,
            height=14,
            bg=self.colors["card"],
            bd=0,
            highlightthickness=0,
        )
        self.status_dot.pack(side=tk.LEFT)
        self.status_dot_circle = self.status_dot.create_oval(2, 2, 12, 12, fill=self.colors["danger"], outline="")

        ttk.Label(status_line, textvariable=self.status_chip_var, style="StatusChip.TLabel").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(status_card, textvariable=self.status_var, style="StatusText.TLabel").pack(anchor="w", pady=(8, 0))

        backend_card = ttk.Frame(summary_row, style="CardAlt.TFrame", padding=(16, 14))
        backend_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        ttk.Label(
            backend_card,
            text="BACKEND ACTIVO",
            style="SectionAlt.TLabel",
        ).pack(anchor="w")
        ttk.Label(backend_card, textvariable=self.backend_var, style="BackendValue.TLabel").pack(anchor="w", pady=(8, 0))

        details = ttk.Frame(container, style="Card.TFrame", padding=(16, 14))
        details.pack(fill=tk.X, pady=(12, 0))
        details.columnconfigure(1, weight=1)

        self._build_readonly_field(
            details,
            row=0,
            label="Servidor local",
            variable=self.server_url_var,
            button_text="Copiar URL",
            command=self.copy_server_url,
        )
        self._build_readonly_field(
            details,
            row=1,
            label="Token local",
            variable=self.token_var,
            button_text="Copiar token",
            command=self.copy_token,
        )

        actions = ttk.Frame(container, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(0, 10))

        self.start_button = ttk.Button(actions, text="Iniciar motor", style="Primary.TButton", command=self.start_server)
        self.start_button.pack(side=tk.LEFT, pady=(12, 0))

        self.stop_button = ttk.Button(actions, text="Detener", style="Danger.TButton", command=self.stop_server)
        self.stop_button.pack(side=tk.LEFT, padx=(10, 0), pady=(12, 0))

        clear_btn = ttk.Button(actions, text="Limpiar logs", style="Secondary.TButton", command=self.clear_logs)
        clear_btn.pack(side=tk.RIGHT, pady=(12, 0))

        log_card = ttk.Frame(container, style="Card.TFrame", padding=(14, 12))
        log_card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        ttk.Label(log_card, text="LOGS", style="Section.TLabel").pack(anchor="w")

        self.logs = scrolledtext.ScrolledText(
            log_card,
            wrap=tk.WORD,
            font=("Cascadia Mono", 10),
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.logs.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.logs.configure(state=tk.DISABLED)
        self._set_stopped_state()

    def _build_readonly_field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        button_text: str,
        command: Any,
    ) -> None:
        ttk.Label(parent, text=label, style="FieldLabel.TLabel").grid(row=row, column=0, sticky="w", pady=(0 if row == 0 else 10, 0))
        entry = ttk.Entry(parent, textvariable=variable, style="ReadOnly.TEntry")
        entry.state(["readonly"])
        entry.grid(row=row, column=1, sticky="ew", padx=(10, 10), pady=(0 if row == 0 else 10, 0))
        ttk.Button(parent, text=button_text, style="Secondary.TButton", command=command).grid(
            row=row,
            column=2,
            sticky="e",
            pady=(0 if row == 0 else 10, 0),
        )

    def enqueue_log(self, message: str) -> None:
        timestamped = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        self._append_persistent_log(timestamped)
        self.log_queue.put(timestamped)

    def _append_persistent_log(self, message: str) -> None:
        try:
            with self.log_file_path.open("a", encoding="utf-8") as stream:
                stream.write(f"{message}\n")
        except Exception:
            # Avoid breaking the launcher UI because of log file IO issues.
            pass

    def flush_logs(self) -> None:
        pending: list[str] = []
        try:
            while True:
                message = self.log_queue.get_nowait()
                pending.append(message)
        except queue.Empty:
            pass
        finally:
            if pending:
                self.logs.configure(state=tk.NORMAL)
                for message in pending:
                    self.logs.insert(tk.END, f"{message}\n")
                self.logs.see(tk.END)
                self.logs.configure(state=tk.DISABLED)
            try:
                if self.root.winfo_exists():
                    self.root.after(200, self.flush_logs)
            except tk.TclError:
                pass

    def copy_token(self) -> None:
        self._copy_to_clipboard(self.runtime.api_token)
        self.enqueue_log("Token local copiado al portapapeles.")

    def copy_server_url(self) -> None:
        self._copy_to_clipboard(self.server_url_var.get())
        self.enqueue_log("URL de servidor local copiada.")

    def _copy_to_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()

    def clear_logs(self) -> None:
        self.logs.configure(state=tk.NORMAL)
        self.logs.delete("1.0", tk.END)
        self.logs.configure(state=tk.DISABLED)
        self.enqueue_log("Logs limpiados.")

    def _set_status_indicator(self, color: str) -> None:
        self.status_dot.itemconfigure(self.status_dot_circle, fill=color)

    def _set_running_state(self) -> None:
        self.status_var.set("Activo y escuchando en localhost")
        self.status_chip_var.set("ONLINE")
        self._set_status_indicator(self.colors["accent"])
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)

    def _set_stopping_state(self) -> None:
        self.status_var.set("Deteniendo motor local...")
        self.status_chip_var.set("STOPPING")
        self._set_status_indicator(self.colors["warning"])
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)

    def _set_stopped_state(self) -> None:
        self.status_var.set("Detenido")
        self.status_chip_var.set("OFFLINE")
        self._set_status_indicator(self.colors["danger"])
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)

    def start_server(self) -> None:
        if self.is_running:
            return
        try:
            import uvicorn
        except ModuleNotFoundError:
            messagebox.showerror(
                "Dependencias faltantes",
                "No se encontro 'uvicorn'.\n\nEjecuta:\n.\\local_engine_windows\\run_local_engine.bat",
            )
            self.enqueue_log("ERROR: uvicorn no disponible. Ejecuta run_local_engine.bat.")
            return

        try:
            # In frozen builds, uvicorn's default LOGGING_CONFIG can fail while
            # resolving formatter classes (e.g., "default"), so we disable it.
            config = uvicorn.Config(
                self.api_app,
                host=DEFAULT_HOST,
                port=DEFAULT_PORT,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            self.server = uvicorn.Server(config)
        except Exception as error:  # noqa: BLE001
            self.enqueue_log(f"ERROR: no se pudo configurar el servidor: {error}")
            messagebox.showerror("Studio Voice Local Engine", f"No se pudo iniciar el servidor local:\n{error}")
            self._set_stopped_state()
            return

        self.server_thread = threading.Thread(target=self._server_run, daemon=True)
        self.server_thread.start()
        self.is_running = True
        self._set_running_state()
        self.enqueue_log("Servidor local iniciado.")

    def _server_run(self) -> None:
        if self.server is None:
            return
        try:
            self.server.run()
        except Exception as error:  # noqa: BLE001
            self.enqueue_log(f"ERROR: fallo en servidor local: {error}")
            self._ui_after(lambda: messagebox.showerror("Servidor local", f"Error en servidor: {error}"))
        finally:
            self._ui_after(self._on_server_thread_stopped)

    def _ui_after(self, callback: Any) -> None:
        try:
            if self.root.winfo_exists():
                self.root.after(0, callback)
        except tk.TclError:
            return

    def _on_server_thread_stopped(self) -> None:
        was_running = self.is_running
        self.is_running = False
        self.server = None
        self.server_thread = None
        self._set_stopped_state()
        if was_running:
            self.enqueue_log("Servidor local detenido.")

    def stop_server(self) -> None:
        if not self.is_running or self.server is None:
            return
        self._set_stopping_state()
        self.enqueue_log("Solicitud de parada enviada.")
        self.server.should_exit = True

    def handle_close(self) -> None:
        self.stop_server()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    window = LocalEngineWindow()
    window.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        messagebox.showerror("Studio Voice Local Engine", f"Error al iniciar: {error}")
