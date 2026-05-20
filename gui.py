import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import usb_manager
from agent import GrokAgent
from voice import VoiceRecorder

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT    = "#1f6feb"
BG_CARD   = "#1e1e2e"
BG_CHAT   = "#13131f"
BG_BUBBLE = "#252538"
BG_ERROR  = "#3a1a1a"


class USBAgentApp(ctk.CTk):
    def __init__(self, api_key: str):
        super().__init__()
        self.agent = GrokAgent(api_key)
        self.voice = VoiceRecorder(api_key)
        self.usb_drives: list = []
        self.selected_usb: dict | None = None
        self.windows_path = str(Path.home() / "Desktop")
        self.usb_path: str | None = None
        self.win_items: list = []
        self.usb_items: list = []
        self._typing_frame = None
        self._is_recording = False

        self.title("USB File Transfer Agent  •  Powered by Groq (Llama 3.3)")
        self.geometry("1100x820")
        self.minsize(900, 660)

        self._build_ui()
        self.after(200, self.refresh_drives)

    # ──────────────────────────────────────────────
    # UI BUILD
    # ──────────────────────────────────────────────

    def _build_ui(self):
        self._build_topbar()
        self._build_panels()
        self._build_chat_bar()
        self._build_statusbar()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=BG_CARD)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar, text="  USB File Transfer Agent",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            bar, text="⟳  Refresh Drives", width=140, height=34,
            command=self.refresh_drives,
        ).pack(side="right", padx=12, pady=10)

        self.usb_var = ctk.StringVar(value="No USB detected")
        self.usb_dropdown = ctk.CTkOptionMenu(
            bar, variable=self.usb_var,
            values=["No USB detected"],
            command=self._on_usb_select,
            width=220, height=34,
        )
        self.usb_dropdown.pack(side="right", padx=(0, 6), pady=10)
        ctk.CTkLabel(bar, text="USB Drive:", font=ctk.CTkFont(size=12)).pack(
            side="right", padx=(0, 2)
        )

    def _build_panels(self):
        wrapper = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, padx=10, pady=6)

        # Left – Windows
        self.left = ctk.CTkFrame(wrapper, corner_radius=10)
        self.left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._panel_header(self.left, "💻  Windows", is_windows=True)

        self.win_path_label = ctk.CTkLabel(
            self.left, text=self.windows_path,
            font=ctk.CTkFont(size=10), text_color="gray", anchor="w",
        )
        self.win_path_label.pack(fill="x", padx=12, pady=(0, 4))

        self.win_scroll = ctk.CTkScrollableFrame(self.left, corner_radius=6)
        self.win_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Middle – Action buttons
        mid = ctk.CTkFrame(wrapper, width=120, corner_radius=10, fg_color=BG_CARD)
        mid.pack(side="left", fill="y", padx=4)
        mid.pack_propagate(False)
        self._build_mid_buttons(mid)

        # Right – USB
        self.right = ctk.CTkFrame(wrapper, corner_radius=10)
        self.right.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self._panel_header(self.right, "🔌  USB Drive", is_windows=False)

        self.usb_path_label = ctk.CTkLabel(
            self.right, text="No USB selected",
            font=ctk.CTkFont(size=10), text_color="gray", anchor="w",
        )
        self.usb_path_label.pack(fill="x", padx=12, pady=(0, 4))

        self.usb_scroll = ctk.CTkScrollableFrame(self.right, corner_radius=6)
        self.usb_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _panel_header(self, parent, title: str, *, is_windows: bool):
        hdr = ctk.CTkFrame(parent, height=42, corner_radius=0, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(8, 2))
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=4
        )
        side_key = "windows" if is_windows else "usb"
        ctk.CTkButton(
            hdr, text="↑ Up", width=52, height=28,
            command=lambda s=side_key: self._go_up(s),
        ).pack(side="right", padx=2)
        if is_windows:
            ctk.CTkButton(
                hdr, text="Browse", width=70, height=28,
                command=self._browse_windows,
            ).pack(side="right", padx=2)

    def _build_mid_buttons(self, parent):
        ctk.CTkLabel(parent, text="Transfer", font=ctk.CTkFont(weight="bold")).pack(pady=(18, 8))

        for label, action, direction in [
            ("Copy →\nto USB", "copy", "win_to_usb"),
            ("Move →\nto USB", "move", "win_to_usb"),
        ]:
            ctk.CTkButton(
                parent, text=label, height=52,
                command=lambda a=action, d=direction: self._transfer(a, d),
            ).pack(padx=10, pady=4, fill="x")

        ctk.CTkLabel(parent, text="─────").pack(pady=4)

        for label, action, direction in [
            ("← Copy\nto PC", "copy", "usb_to_win"),
            ("← Move\nto PC", "move", "usb_to_win"),
        ]:
            ctk.CTkButton(
                parent, text=label, height=52,
                command=lambda a=action, d=direction: self._transfer(a, d),
            ).pack(padx=10, pady=4, fill="x")

        ctk.CTkLabel(
            parent, text="✓ check files\nfirst",
            font=ctk.CTkFont(size=10), text_color="gray",
        ).pack(pady=8)

    # ──────────────────────────────────────────────
    # CHAT BAR
    # ──────────────────────────────────────────────

    def _build_chat_bar(self):
        self._drag_start_y = 0
        self._drag_start_height = 0

        self.bottom_frame = ctk.CTkFrame(self, height=280, corner_radius=0, fg_color=BG_CARD)
        self.bottom_frame.pack(fill="x")
        self.bottom_frame.pack_propagate(False)

        # ── Drag handle ──
        handle = ctk.CTkFrame(
            self.bottom_frame, height=14, cursor="sb_v_double_arrow",
            fg_color="#1a1a2e", corner_radius=0,
        )
        handle.pack(fill="x")
        handle.pack_propagate(False)
        ctk.CTkLabel(
            handle, text="───────────────",
            font=ctk.CTkFont(size=8), text_color="#444466",
        ).pack(expand=True)
        for widget in [handle] + handle.winfo_children():
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_motion)

        # ── Chat header row ──
        hdr = ctk.CTkFrame(self.bottom_frame, fg_color="transparent", height=36)
        hdr.pack(fill="x", padx=12, pady=(8, 4))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🤖  AI Assistant",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            hdr, text="Clear chat", width=80, height=26,
            fg_color="#2a2a44", hover_color="#3a3a5e",
            font=ctk.CTkFont(size=11),
            command=self._clear_chat,
        ).pack(side="right", padx=2)

        ctk.CTkLabel(
            hdr,
            text='Try: "move report.pdf to USB"  •  "copy all .jpg to Desktop"',
            font=ctk.CTkFont(size=10), text_color="#555577",
        ).pack(side="left", padx=12)

        # ── Messages area ──
        self.chat_messages = ctk.CTkScrollableFrame(
            self.bottom_frame, fg_color=BG_CHAT, corner_radius=10,
        )
        self.chat_messages.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # ── Input row ──
        input_row = ctk.CTkFrame(self.bottom_frame, fg_color="transparent", height=48)
        input_row.pack(fill="x", padx=10, pady=(0, 10))
        input_row.pack_propagate(False)

        self.chat_input = ctk.CTkEntry(
            input_row,
            placeholder_text="Ask the AI anything, or press 🎤 to speak…",
            height=42, corner_radius=21,
            border_width=1, border_color="#2e2e4e",
            font=ctk.CTkFont(size=12),
        )
        self.chat_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.chat_input.bind("<Return>", lambda _e: self._send_chat())

        self.mic_btn = ctk.CTkButton(
            input_row, text="🎤", width=42, height=42,
            corner_radius=21,
            fg_color="#2a2a44", hover_color="#3a3a5e",
            font=ctk.CTkFont(size=16),
            command=self._toggle_recording,
        )
        self.mic_btn.pack(side="right", padx=(0, 8))

        self.send_btn = ctk.CTkButton(
            input_row, text="↑", width=42, height=42,
            corner_radius=21,
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self._send_chat,
        )
        self.send_btn.pack(side="right")

    def _drag_start(self, event):
        self._drag_start_y = event.y_root
        self._drag_start_height = self.bottom_frame.winfo_height()

    def _drag_motion(self, event):
        delta = self._drag_start_y - event.y_root
        new_height = max(120, min(560, self._drag_start_height + delta))
        self.bottom_frame.configure(height=new_height)

    # ──────────────────────────────────────────────
    # STATUS BAR
    # ──────────────────────────────────────────────

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#111122")
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            bar, text="Ready", font=ctk.CTkFont(size=11), text_color="#aaaacc"
        )
        self.status_label.pack(side="left", padx=14)

        self.progress = ctk.CTkProgressBar(bar, width=180, height=10)
        self.progress.set(0)
        self.progress.pack(side="right", padx=14, pady=8)
        self.progress.pack_forget()

    # ──────────────────────────────────────────────
    # DRIVE MANAGEMENT
    # ──────────────────────────────────────────────

    def refresh_drives(self):
        self.usb_drives = usb_manager.get_usb_drives()
        if self.usb_drives:
            labels = [f"{d['label']} ({d['mountpoint']})" for d in self.usb_drives]
            self.usb_dropdown.configure(values=labels)
            self.usb_var.set(labels[0])
            self._on_usb_select(labels[0])
            self._set_status(f"{len(self.usb_drives)} USB drive(s) detected.")
        else:
            self.usb_dropdown.configure(values=["No USB detected"])
            self.usb_var.set("No USB detected")
            self.usb_path = None
            self.usb_path_label.configure(text="No USB selected")
            self._refresh_usb_list()
            self._set_status("No USB drive found. Please plug in a USB drive and click Refresh.")
        self._refresh_win_list()

    def _on_usb_select(self, value: str):
        for drive in self.usb_drives:
            if f"{drive['label']} ({drive['mountpoint']})" == value:
                self.selected_usb = drive
                self.usb_path = drive["mountpoint"]
                self.usb_path_label.configure(text=self.usb_path)
                self._refresh_usb_list()
                return

    def _browse_windows(self):
        path = filedialog.askdirectory(initialdir=self.windows_path)
        if path:
            self.windows_path = path
            self.win_path_label.configure(text=path)
            self._refresh_win_list()

    def _go_up(self, side: str):
        if side == "windows":
            parent = str(Path(self.windows_path).parent)
            if parent != self.windows_path:
                self.windows_path = parent
                self.win_path_label.configure(text=parent)
                self._refresh_win_list()
        elif side == "usb" and self.usb_path:
            parent = str(Path(self.usb_path).parent)
            if parent != self.usb_path:
                self.usb_path = parent
                self.usb_path_label.configure(text=parent)
                self._refresh_usb_list()

    # ──────────────────────────────────────────────
    # FILE LIST RENDERING
    # ──────────────────────────────────────────────

    def _refresh_win_list(self):
        self._clear_frame(self.win_scroll)
        self.win_items = []
        files = usb_manager.list_directory(self.windows_path)
        if files:
            for item in files:
                self._make_row(self.win_scroll, item, "windows")
        else:
            ctk.CTkLabel(self.win_scroll, text="Empty folder", text_color="gray").pack(pady=20)

    def _refresh_usb_list(self):
        self._clear_frame(self.usb_scroll)
        self.usb_items = []
        if not self.usb_path:
            ctk.CTkLabel(self.usb_scroll, text="No USB drive selected", text_color="gray").pack(pady=20)
            return
        files = usb_manager.list_directory(self.usb_path)
        if files:
            for item in files:
                self._make_row(self.usb_scroll, item, "usb")
        else:
            ctk.CTkLabel(self.usb_scroll, text="Empty folder", text_color="gray").pack(pady=20)

    def _make_row(self, parent, item: dict, side: str):
        row = ctk.CTkFrame(parent, height=28, fg_color="transparent", corner_radius=4)
        row.pack(fill="x", pady=1)

        icon = "📁" if item["is_dir"] else self._file_icon(item["name"])
        var = ctk.BooleanVar()

        cb = ctk.CTkCheckBox(
            row, text=f"{icon}  {item['name']}",
            variable=var, height=24,
            font=ctk.CTkFont(size=12),
        )
        cb.pack(side="left", padx=6)

        if not item["is_dir"]:
            ctk.CTkLabel(
                row, text=usb_manager.format_size(item["size"]),
                text_color="gray", font=ctk.CTkFont(size=10),
            ).pack(side="right", padx=8)

        def on_double(event, path=item["path"], is_dir=item["is_dir"], s=side):
            if is_dir:
                if s == "windows":
                    self.windows_path = path
                    self.win_path_label.configure(text=path)
                    self._refresh_win_list()
                else:
                    self.usb_path = path
                    self.usb_path_label.configure(text=path)
                    self._refresh_usb_list()

        row.bind("<Double-Button-1>", on_double)
        cb.bind("<Double-Button-1>", on_double)

        if side == "windows":
            self.win_items.append((var, item))
        else:
            self.usb_items.append((var, item))

    # ──────────────────────────────────────────────
    # TRANSFER OPERATIONS
    # ──────────────────────────────────────────────

    def _transfer(self, action: str, direction: str):
        if direction == "win_to_usb":
            if not self.usb_path:
                messagebox.showerror("No USB", "Please select a USB drive first.")
                return
            selected = [item for var, item in self.win_items if var.get() and not item["is_dir"]]
            dst = self.usb_path
        else:
            selected = [item for var, item in self.usb_items if var.get() and not item["is_dir"]]
            dst = self.windows_path

        if not selected:
            messagebox.showwarning("No files selected", "Please check the files you want to transfer.")
            return

        def run():
            self.after(0, lambda: self.progress.pack(side="right", padx=14, pady=8))
            total = len(selected)
            fn = usb_manager.copy_file if action == "copy" else usb_manager.move_file
            ok = 0
            for i, item in enumerate(selected):
                self.after(0, lambda n=item["name"]: self._set_status(
                    f"{'Copying' if action == 'copy' else 'Moving'}: {n}"
                ))
                self.after(0, lambda v=(i + 1) / total: self.progress.set(v))
                success, _ = fn(item["path"], dst)
                if success:
                    ok += 1
            self.after(0, lambda: self.progress.pack_forget())
            self.after(0, lambda: self._set_status(f"Done — {action.capitalize()}d {ok}/{total} file(s)."))
            self.after(0, self._refresh_win_list)
            self.after(0, self._refresh_usb_list)

        threading.Thread(target=run, daemon=True).start()

    # ──────────────────────────────────────────────
    # CHAT — messages & input
    # ──────────────────────────────────────────────

    def _toggle_recording(self):
        if self._is_recording:
            # Stop recording and transcribe
            self._is_recording = False
            self.mic_btn.configure(text="🎤", fg_color="#2a2a44", hover_color="#3a3a5e")
            self._set_status("Transcribing…")

            def transcribe():
                try:
                    text = self.voice.stop_and_transcribe()
                    if text:
                        self.after(0, lambda: self.chat_input.delete(0, "end"))
                        self.after(0, lambda: self.chat_input.insert(0, text))
                        self.after(0, lambda: self._set_status(f"Heard: {text}"))
                    else:
                        self.after(0, lambda: self._set_status("Nothing heard. Try again."))
                except Exception as e:
                    self.after(0, lambda err=e: self._set_status(f"Transcription error: {err}"))

            threading.Thread(target=transcribe, daemon=True).start()
        else:
            # Start recording
            self._is_recording = True
            self.mic_btn.configure(text="⏹", fg_color="#aa2222", hover_color="#cc3333")
            self._set_status("🎤 Recording… click ⏹ to stop")
            self.voice.start()

    def _send_chat(self):
        msg = self.chat_input.get().strip()
        if not msg:
            return
        self.chat_input.delete(0, "end")

        if msg.lower() in ("clear", "/clear"):
            self._clear_chat()
            return

        self.send_btn.configure(state="disabled", fg_color="#333355")
        self._add_bubble(msg, "user")
        self._show_typing()

        def ask():
            try:
                reply = self.agent.chat(msg, usb_path=self.usb_path, windows_path=self.windows_path)
                self.after(0, self._hide_typing)
                self.after(0, lambda: self._add_bubble(reply, "ai"))
                self.after(0, self._refresh_win_list)
                self.after(0, self._refresh_usb_list)
            except Exception as e:
                self.after(0, self._hide_typing)
                self.after(0, lambda err=e: self._add_bubble(str(err), "error"))
            finally:
                self.after(0, lambda: self.send_btn.configure(state="normal", fg_color=ACCENT))

        threading.Thread(target=ask, daemon=True).start()

    def _add_bubble(self, text: str, sender: str):
        """sender: 'user' | 'ai' | 'error'"""
        is_user = sender == "user"
        is_error = sender == "error"
        time_str = datetime.now().strftime("%H:%M")

        # Meta row (name + time)
        meta = ctk.CTkFrame(self.chat_messages, fg_color="transparent")
        meta.pack(fill="x", padx=8, pady=(8, 1))
        name = "You" if is_user else ("⚠ Error" if is_error else "Grok AI")
        name_color = "#888aaa" if not is_error else "#cc6666"
        ctk.CTkLabel(
            meta, text=f"{name}  {time_str}",
            font=ctk.CTkFont(size=9), text_color=name_color,
        ).pack(side="right" if is_user else "left")

        # Bubble row
        bubble_row = ctk.CTkFrame(self.chat_messages, fg_color="transparent")
        bubble_row.pack(fill="x", padx=8, pady=(0, 2))

        if is_error:
            bg = BG_ERROR
        elif is_user:
            bg = ACCENT
        else:
            bg = BG_BUBBLE

        bubble = ctk.CTkFrame(bubble_row, fg_color=bg, corner_radius=14)
        bubble.pack(
            side="right" if is_user else "left",
            padx=(80, 0) if is_user else (0, 80),
        )

        ctk.CTkLabel(
            bubble, text=text,
            wraplength=400,
            justify="right" if is_user else "left",
            font=ctk.CTkFont(size=12),
            text_color="#ffaaaa" if is_error else "white",
            anchor="w",
        ).pack(padx=14, pady=9)

        self._scroll_to_bottom()

    def _show_typing(self):
        self._typing_frame = ctk.CTkFrame(self.chat_messages, fg_color="transparent")
        self._typing_frame.pack(fill="x", padx=8, pady=(4, 2))
        bubble = ctk.CTkFrame(self._typing_frame, fg_color=BG_BUBBLE, corner_radius=14)
        bubble.pack(side="left")
        ctk.CTkLabel(
            bubble, text="Grok is thinking…",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#666688",
        ).pack(padx=14, pady=8)
        self._scroll_to_bottom()

    def _hide_typing(self):
        if self._typing_frame:
            self._typing_frame.destroy()
            self._typing_frame = None

    def _clear_chat(self):
        self.agent.reset()
        for w in self.chat_messages.winfo_children():
            w.destroy()
        self._set_status("Chat cleared.")

    def _scroll_to_bottom(self):
        self.after(60, lambda: self.chat_messages._parent_canvas.yview_moveto(1.0))

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.status_label.configure(text=msg)

    @staticmethod
    def _clear_frame(frame):
        for w in frame.winfo_children():
            w.destroy()

    @staticmethod
    def _file_icon(name: str) -> str:
        ext = Path(name).suffix.lower()
        return {
            ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".bmp": "🖼️",
            ".mp4": "🎬", ".mov": "🎬", ".avi": "🎬", ".mkv": "🎬",
            ".mp3": "🎵", ".wav": "🎵", ".flac": "🎵",
            ".pdf": "📕", ".doc": "📝", ".docx": "📝", ".txt": "📄",
            ".zip": "🗜️", ".rar": "🗜️", ".7z": "🗜️",
            ".exe": "⚙️", ".msi": "⚙️",
        }.get(ext, "📄")
