import os
import sys
import json
import asyncio
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path

from src.scanner import scan_project
from src.context_extractor import extract_context
from src.agent_builder import build_agent_prompts
from src.llm_generator import generate_hybrid, generate_pure_llm_sync
from src.ide_exporter import export_to_ide, IDE_FORMATS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


HTTP_ERROR_MESSAGES = {
    400: "Bad request — check your request format",
    401: "Unauthorized — invalid or missing API key. Check your key at the provider dashboard.",
    402: "Payment required — add credits to your account",
    403: "Forbidden — API key does not have permission for this model",
    404: "Not found — model name is incorrect or endpoint URL is wrong",
    429: "Rate limited — too many requests or no credits. Try a free model or add credits.",
    500: "Server error — the provider is having issues, try again later",
    502: "Bad gateway — the provider is unreachable",
    503: "Service unavailable — the provider is down for maintenance",
    504: "Gateway timeout — the request took too long",
}


def _http_error(code: int, body: str) -> str:
    friendly = HTTP_ERROR_MESSAGES.get(code, f"HTTP {code}")
    try:
        import json as _json
        data = _json.loads(body)
        detail = data.get("error", {}).get("message", "") or data.get("message", "")
        if detail:
            return f"{friendly}\nDetails: {detail[:200]}"
    except (ValueError, KeyError):
        pass
    return friendly


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings: dict, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title("LLM Settings")
        self.geometry("450x350")
        self.resizable(False, False)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="Provider", font=("", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 2))
        PROVIDER_URLS = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "openai-compatible": "",
            "qwen": "https://api.qwen.ai/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "ollama": "http://localhost:11434/v1",
            "custom": "",
        }

        self.provider_var = ctk.StringVar(value=settings.get("provider", "openai"))
        provider_combo = ctk.CTkComboBox(frame, values=list(PROVIDER_URLS.keys()), variable=self.provider_var, width=280)
        provider_combo.grid(row=0, column=1, pady=(0, 10))

        ctk.CTkLabel(frame, text="Base URL", font=("", 12, "bold")).grid(row=1, column=0, sticky="w", pady=(0, 2))
        self.base_url_var = ctk.StringVar(value=settings.get("base_url", "https://api.openai.com/v1"))
        ctk.CTkEntry(frame, textvariable=self.base_url_var, width=280).grid(row=1, column=1, pady=(0, 10))

        ctk.CTkLabel(frame, text="Model", font=("", 12, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.model_var = ctk.StringVar(value=settings.get("model", "gpt-4o"))
        ctk.CTkEntry(frame, textvariable=self.model_var, width=280).grid(row=2, column=1, pady=(0, 10))

        ctk.CTkLabel(frame, text="API Key", font=("", 12, "bold")).grid(row=3, column=0, sticky="w", pady=(0, 2))
        self.api_key_var = ctk.StringVar(value=settings.get("api_key", ""))
        ctk.CTkEntry(frame, textvariable=self.api_key_var, show="*", width=280).grid(row=3, column=1, pady=(0, 10))

        show_key_var = ctk.BooleanVar(value=False)

        def toggle_show():
            if show_key_var.get():
                for child in frame.winfo_children():
                    if isinstance(child, ctk.CTkEntry) and child.cget("show") == "*":
                        child.configure(show="")
            else:
                for child in frame.winfo_children():
                    if isinstance(child, ctk.CTkEntry) and child.cget("show") == "":
                        child.configure(show="*")

        ctk.CTkCheckBox(frame, text="Show API Key", variable=show_key_var, command=toggle_show).grid(row=4, column=1, sticky="w", pady=(0, 10))

        def on_provider_change(*_):
            provider = self.provider_var.get()
            url = PROVIDER_URLS.get(provider, "")
            if url:
                self.base_url_var.set(url)

        self.provider_var.trace_add("write", on_provider_change)

        btn_frame = ctk.CTkFrame(frame)
        btn_frame.grid(row=5, column=1, sticky="e")
        self.test_btn = ctk.CTkButton(btn_frame, text="Test Connection", width=120, command=self._test_connection)
        self.test_btn.pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="Save", width=80, command=self._save).pack(side="left", padx=3)

        self.test_label = ctk.CTkLabel(frame, text="", font=("", 10))
        self.test_label.grid(row=6, column=1, sticky="w", pady=(5, 0))

    def _save(self):
        settings = {
            "provider": self.provider_var.get(),
            "base_url": self.base_url_var.get().strip(),
            "model": self.model_var.get().strip(),
            "api_key": self.api_key_var.get().strip().strip("'\""),
        }
        self.on_save(settings)
        self.destroy()

    def _test_connection(self):
        import requests

        api_key = self.api_key_var.get().strip().strip("'\"")
        base_url = self.base_url_var.get().strip().rstrip("/")
        model = self.model_var.get().strip()

        key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "(too short)"

        if base_url == "https://openrouter.ai/api/v1" and not api_key.startswith("sk-or-v1-"):
            self.test_label.configure(
                text="Invalid key format. OpenRouter keys start with 'sk-or-v1-'\nGo to openrouter.ai/keys to get your key.",
                text_color="red",
            )
            return

        self.test_label.configure(text=f"Testing... Key: {key_preview}", text_color="yellow")
        self.test_btn.configure(state="disabled")

        def do_test():
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ai-cto-generator.local",
                "X-OpenRouter-Title": "AI CTO Generator",
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with just: pong"}],
                "max_tokens": 5,
            }

            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return True, f"Connected ({content.strip()})"
                else:
                    err_text = resp.text[:500]
                    debug_info = f"HTTP {resp.status_code}\nURL: {url}\nKey: {key_preview}\nModel: {model}\nAuth header: Bearer {key_preview}\nHeaders sent: {list(headers.keys())}\nResponse: {err_text}"
                    return False, debug_info

            except requests.exceptions.ConnectionError:
                return False, f"Cannot reach {base_url}\nCheck your internet connection and proxy settings."
            except requests.exceptions.Timeout:
                return False, "Request timed out (30s). The provider is slow or unreachable."
            except Exception as e:
                return False, f"Error: {str(e)[:200]}"

        success, msg = do_test()
        self.test_btn.configure(state="normal")
        if success:
            self.test_label.configure(text=msg, text_color="green")
        else:
            self.test_label.configure(text=msg, text_color="red")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI CTO Agent Generator")
        self.geometry("700x720")
        self.resizable(False, False)

        self.project_path = ""
        self.output_path = ""
        self.mode_var = ctk.StringVar(value="hybrid")
        self.selected_ides = set(IDE_FORMATS.keys())
        self.settings = {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "api_key": "",
            "output_in_project": True,
            "custom_output": "",
        }
        self.pure_llm_description = ""

        self._load_settings()
        self._build_ui()

    def _load_settings(self):
        settings_path = Path(__file__).parent.parent / "gui_settings.json"
        if settings_path.exists():
            try:
                self.settings = json.loads(settings_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    def _save_settings(self, settings=None):
        if settings:
            self.settings = settings
        settings_path = Path(__file__).parent.parent / "gui_settings.json"
        settings_path.write_text(json.dumps(self.settings))

    def _build_ui(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=20, pady=15)

        self._build_mode_section(main)
        self._build_project_section(main)
        self._build_output_dir_section(main)
        self._build_settings_section(main)
        self._build_ide_section(main)
        self._build_pure_llm_section(main)
        self._build_generate_section(main)
        self._build_output_section(main)

    def _build_mode_section(self, parent):
        mode_frame = ctk.CTkFrame(parent)
        mode_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(mode_frame, text="Mode:", font=("", 13, "bold")).pack(side="left", padx=(15, 10), pady=10)

        modes = [
            ("scanner", "Scanner-only (offline)"),
            ("hybrid", "Hybrid (scanner + LLM)"),
            ("pure_llm", "Pure LLM (no scan)"),
        ]
        for value, label in modes:
            ctk.CTkRadioButton(mode_frame, text=label, variable=self.mode_var, value=value, command=self._on_mode_change).pack(side="left", padx=8, pady=10)

    def _build_project_section(self, parent):
        proj_frame = ctk.CTkFrame(parent)
        proj_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(proj_frame, text="Project:", font=("", 13, "bold")).pack(side="left", padx=(15, 10), pady=10)

        self.path_var = ctk.StringVar(value="No project selected")
        path_entry = ctk.CTkEntry(proj_frame, textvariable=self.path_var, width=380, state="readonly")
        path_entry.pack(side="left", padx=5, pady=10)

        ctk.CTkButton(proj_frame, text="Browse", width=80, command=self._browse_project).pack(side="left", padx=5, pady=10)

    def _build_output_dir_section(self, parent):
        out_frame = ctk.CTkFrame(parent)
        out_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(out_frame, text="Save to:", font=("", 13, "bold")).pack(side="left", padx=(15, 10), pady=10)

        self.save_mode_var = ctk.StringVar(value="project" if self.settings.get("output_in_project", True) else "custom")

        ctk.CTkRadioButton(out_frame, text="Project root", variable=self.save_mode_var, value="project", command=self._on_save_mode_change).pack(side="left", padx=8, pady=10)
        ctk.CTkRadioButton(out_frame, text="Custom folder", variable=self.save_mode_var, value="custom", command=self._on_save_mode_change).pack(side="left", padx=8, pady=10)

        self.custom_path_var = ctk.StringVar(value=self.settings.get("custom_output", ""))
        self.custom_path_entry = ctk.CTkEntry(out_frame, textvariable=self.custom_path_var, width=250, state="readonly")
        self.custom_path_entry.pack(side="left", padx=5, pady=10)

        self.custom_browse_btn = ctk.CTkButton(out_frame, text="Browse", width=80, command=self._browse_output)
        self.custom_browse_btn.pack(side="left", padx=5, pady=10)

        self._on_save_mode_change()

    def _on_save_mode_change(self):
        mode = self.save_mode_var.get()
        if mode == "custom":
            self.custom_path_entry.configure(state="normal")
            self.custom_browse_btn.configure(state="normal")
        else:
            self.custom_path_entry.configure(state="readonly")
            self.custom_browse_btn.configure(state="disabled")

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.output_path = path
            self.custom_path_var.set(path)

    def _build_settings_section(self, parent):
        settings_frame = ctk.CTkFrame(parent)
        settings_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(settings_frame, text="LLM:", font=("", 13, "bold")).pack(side="left", padx=(15, 10), pady=10)

        self.llm_status_var = ctk.StringVar(value=f"{self.settings['provider']} / {self.settings['model']}")
        ctk.CTkLabel(settings_frame, textvariable=self.llm_status_var).pack(side="left", padx=5, pady=10)

        ctk.CTkButton(settings_frame, text="Settings", width=80, command=self._open_settings).pack(side="right", padx=15, pady=10)

    def _build_ide_section(self, parent):
        ide_frame = ctk.CTkFrame(parent)
        ide_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(ide_frame, text="Target IDEs:", font=("", 13, "bold")).pack(side="left", padx=(15, 10), pady=10)

        self.ide_vars = {}
        for i, (key, info) in enumerate(IDE_FORMATS.items()):
            var = ctk.BooleanVar(value=True)
            self.ide_vars[key] = var
            ctk.CTkCheckBox(ide_frame, text=key.capitalize(), variable=var).pack(side="left", padx=6, pady=10)

        ctk.CTkButton(ide_frame, text="All", width=50, command=self._select_all_ides).pack(side="right", padx=3, pady=10)
        ctk.CTkButton(ide_frame, text="None", width=50, command=self._deselect_all_ides).pack(side="right", padx=3, pady=10)

    def _build_pure_llm_section(self, parent):
        self.pure_frame = ctk.CTkFrame(parent)

        ctk.CTkLabel(self.pure_frame, text="Project Description:", font=("", 12, "bold")).pack(anchor="w", padx=15, pady=(10, 2))
        self.pure_text = ctk.CTkTextbox(self.pure_frame, height=80, width=640)
        self.pure_text.pack(fill="x", padx=15, pady=(0, 10))
        self.pure_text.insert("1.0", "Describe your project: language, framework, architecture, key files, conventions...\n\nExample: FastAPI + React + PostgreSQL. Backend in src/, frontend in web/. Uses pytest, eslint, Docker. Async endpoints, JWT auth, Prisma ORM.")

        self._on_mode_change()

    def _build_generate_section(self, parent):
        gen_frame = ctk.CTkFrame(parent)
        gen_frame.pack(fill="x", pady=(0, 10))

        self.generate_btn = ctk.CTkButton(gen_frame, text="Generate", font=("", 14, "bold"), height=40, command=self._generate)
        self.generate_btn.pack(fill="x", padx=15, pady=10)

    def _build_output_section(self, parent):
        out_frame = ctk.CTkFrame(parent)
        out_frame.pack(fill="both", expand=True, pady=(0, 5))

        ctk.CTkLabel(out_frame, text="Output:", font=("", 13, "bold")).pack(anchor="w", padx=15, pady=(10, 2))

        self.output_text = ctk.CTkTextbox(out_frame, height=120, width=640, state="disabled")
        self.output_text.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    def _on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "pure_llm":
            self.pure_frame.pack(fill="x", pady=(0, 10))
        else:
            self.pure_frame.pack_forget()

    def _browse_project(self):
        path = filedialog.askdirectory(title="Select Project Directory")
        if path:
            self.project_path = path
            self.path_var.set(path)

    def _open_settings(self):
        def on_save(settings):
            self.settings = settings
            self._save_settings(settings)
            self.llm_status_var.set(f"{settings['provider']} / {settings['model']}")

        SettingsWindow(self, self.settings, on_save)

    def _select_all_ides(self):
        for var in self.ide_vars.values():
            var.set(True)

    def _deselect_all_ides(self):
        for var in self.ide_vars.values():
            var.set(False)

    def _log(self, msg):
        self.output_text.configure(state="normal")
        self.output_text.insert("end", msg + "\n")
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def _generate(self):
        mode = self.mode_var.get()
        selected_ides = [k for k, v in self.ide_vars.items() if v.get()]

        if mode == "pure_llm":
            self.pure_llm_description = self.pure_text.get("1.0", "end").strip()
            if not self.pure_llm_description:
                messagebox.showwarning("Missing Input", "Please describe your project in the text box.")
                return
            if not self.settings["api_key"]:
                messagebox.showwarning("Missing API Key", "Please set your API key in Settings.")
                return
        else:
            if not self.project_path:
                messagebox.showwarning("Missing Project", "Please select a project directory.")
                return
            if mode != "scanner" and not self.settings["api_key"]:
                messagebox.showwarning("Missing API Key", "Please set your API key in Settings.")
                return

        if not selected_ides:
            messagebox.showwarning("No IDEs Selected", "Please select at least one target IDE.")
            return

        self.generate_btn.configure(state="disabled")
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

        thread = threading.Thread(target=self._run_generation, args=(mode, selected_ides), daemon=True)
        thread.start()

    def _run_generation(self, mode, selected_ides):
        try:
            if mode == "scanner":
                self._log("Scanning project...")
                scan = scan_project(self.project_path)
                self._log(f"Found {scan.total_files} files, {scan.total_dirs} directories")

                self._log("Extracting context...")
                ctx = extract_context(scan)
                self._log(f"Project: {ctx.project_name}")
                self._log(f"Languages: {', '.join(ctx.languages) if ctx.languages else 'N/A'}")
                self._log(f"Frameworks: {', '.join(ctx.frameworks) if ctx.frameworks else 'N/A'}")

                self._log("Building agent prompts...")
                prompts = build_agent_prompts(ctx)

            elif mode == "hybrid":
                self._log("Scanning project...")
                scan = scan_project(self.project_path)
                self._log(f"Found {scan.total_files} files, {scan.total_dirs} directories")

                self._log("Extracting context...")
                ctx = extract_context(scan)
                self._log(f"Project: {ctx.project_name}")
                self._log(f"Frameworks: {', '.join(ctx.frameworks) if ctx.frameworks else 'N/A'}")

                self._log("Generating with LLM (hybrid mode)...")
                self._log("This may take 10-30 seconds...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    prompts = loop.run_until_complete(generate_hybrid(
                        ctx,
                        api_key=self.settings["api_key"].strip().strip("'\""),
                        base_url=self.settings["base_url"].strip(),
                        model=self.settings["model"].strip(),
                    ))
                finally:
                    loop.close()
                self._log("LLM generation complete")

            elif mode == "pure_llm":
                self._log("Generating with LLM (pure mode)...")
                prompts = generate_pure_llm_sync(
                    self.pure_llm_description,
                    api_key=self.settings["api_key"].strip().strip("'\""),
                    base_url=self.settings["base_url"].strip(),
                    model=self.settings["model"].strip(),
                )
                self._log("LLM generation complete")

            save_mode = self.save_mode_var.get()
            if save_mode == "custom" and self.output_path:
                export_path = self.output_path
            else:
                export_path = self.project_path

            self._log("")
            self._log(f"Exporting to {len(selected_ides)} IDE(s)...")
            self._log(f"Output directory: {export_path}")
            generated = export_to_ide(export_path, None, prompts, selected_ides)

            self._log("")
            for g in generated:
                self._log(f"  ✓ {g}")

            self._log("")
            self._log("Done! Open your project in the selected IDE(s).")

        except Exception as e:
            self._log("")
            self._log(f"ERROR: {e}")

        finally:
            self.generate_btn.configure(state="normal")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
