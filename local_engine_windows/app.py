from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

import uvicorn

try:
    from local_engine_windows.daemon import DEFAULT_HOST, DEFAULT_PORT, EngineRuntime, create_app
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution
    from daemon import DEFAULT_HOST, DEFAULT_PORT, EngineRuntime, create_app


class LocalEngineWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Studio Voice Local Engine")
        self.root.geometry("720x520")
        self.root.minsize(640, 480)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.runtime = EngineRuntime(logger=self.enqueue_log)
        self.api_app = create_app(self.runtime)

        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.is_running = False

        self.status_var = tk.StringVar(value="Detenido")
        self.server_url_var = tk.StringVar(value=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}")
        self.token_var = tk.StringVar(value=self.runtime.api_token)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.handle_close)
        self.start_server()
        self.root.after(150, self.flush_logs)

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, padx=12, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="Modo Pro Local Engine",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
            justify=tk.LEFT,
        )
        title.pack(fill=tk.X, pady=(0, 6))

        subtitle = tk.Label(
            container,
            text=(
                "Esta app corre en localhost para burlar limites del navegador y usar tu hardware local.\n"
                "Codigo abierto y auditable. Al cerrar esta ventana, se apaga el motor."
            ),
            justify=tk.LEFT,
            anchor="w",
        )
        subtitle.pack(fill=tk.X, pady=(0, 10))

        status_frame = tk.Frame(container, bd=1, relief=tk.GROOVE, padx=10, pady=8)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(status_frame, text="Estado:").grid(row=0, column=0, sticky="w")
        tk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(8, 0),
        )

        tk.Label(status_frame, text="Servidor:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        server_entry = tk.Entry(status_frame, textvariable=self.server_url_var, state="readonly", width=56)
        server_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

        tk.Label(status_frame, text="Token local:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        token_entry = tk.Entry(status_frame, textvariable=self.token_var, state="readonly", width=56)
        token_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

        actions = tk.Frame(container)
        actions.pack(fill=tk.X, pady=(0, 10))

        self.start_button = tk.Button(actions, text="Iniciar", width=14, command=self.start_server)
        self.start_button.pack(side=tk.LEFT)

        self.stop_button = tk.Button(actions, text="Detener", width=14, command=self.stop_server)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))

        copy_btn = tk.Button(actions, text="Copiar token", width=14, command=self.copy_token)
        copy_btn.pack(side=tk.LEFT, padx=(8, 0))

        logs_label = tk.Label(container, text="Logs")
        logs_label.pack(anchor="w")

        self.logs = scrolledtext.ScrolledText(container, wrap=tk.WORD, font=("Consolas", 10))
        self.logs.pack(fill=tk.BOTH, expand=True)

    def enqueue_log(self, message: str) -> None:
        self.log_queue.put(message)

    def flush_logs(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.logs.insert(tk.END, f"{message}\n")
                self.logs.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(200, self.flush_logs)

    def copy_token(self) -> None:
        token = self.runtime.api_token
        self.root.clipboard_clear()
        self.root.clipboard_append(token)
        self.enqueue_log("Token local copiado al portapapeles.")

    def start_server(self) -> None:
        if self.is_running:
            return

        config = uvicorn.Config(
            self.api_app,
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self._server_run, daemon=True)
        self.server_thread.start()
        self.is_running = True
        self.status_var.set("Activo")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.enqueue_log("Servidor local iniciado.")

    def _server_run(self) -> None:
        if self.server is None:
            return
        self.server.run()
        self.is_running = False
        self.status_var.set("Detenido")
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.enqueue_log("Servidor local detenido.")

    def stop_server(self) -> None:
        if not self.is_running or self.server is None:
            return
        self.server.should_exit = True
        if self.server_thread is not None:
            self.server_thread.join(timeout=5)
        self.is_running = False
        self.status_var.set("Detenido")
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.enqueue_log("Solicitud de parada enviada.")

    def handle_close(self) -> None:
        self.stop_server()
        self.root.destroy()

    def run(self) -> None:
        self.stop_button.configure(state=tk.NORMAL if self.is_running else tk.DISABLED)
        self.root.mainloop()


def main() -> None:
    window = LocalEngineWindow()
    window.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        messagebox.showerror("Studio Voice Local Engine", f"Error al iniciar: {error}")
