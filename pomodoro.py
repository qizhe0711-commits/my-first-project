import tkinter as tk
from tkinter import ttk
import json
import winsound
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "pomodoro_config.json"

# ── Timer Logic ────────────────────────────────────────────────────────

class PomodoroTimer:
    def __init__(self, work_mins=25, short_break_mins=5, long_break_mins=15):
        self.work_secs = work_mins * 60
        self.short_break_secs = short_break_mins * 60
        self.long_break_secs = long_break_mins * 60
        self._reset()
        self._callbacks = {"tick": None, "state_change": None}

    def _reset(self):
        self.state = "idle"
        self.remaining = self.work_secs
        self.total = self.work_secs
        self.session = 0

    def _total_for_state(self, state):
        if state == "working": return self.work_secs
        if state == "short_break": return self.short_break_secs
        if state == "long_break": return self.long_break_secs
        return self.work_secs

    def on(self, event, callback):
        self._callbacks[event] = callback

    def _emit(self, event, *args):
        cb = self._callbacks.get(event)
        if cb: cb(*args)

    def start(self):
        if self.state == "idle":
            self.state = "working"
            self.remaining = self.work_secs
            self.total = self.work_secs
        elif self.state == "paused":
            self.state = self._paused_from
        else:
            return
        self._emit("state_change", self.state)
        self._emit("tick", self.remaining, self.total)

    def pause(self):
        if self.state in ("working", "short_break", "long_break"):
            self._paused_from = self.state
            self.state = "paused"
            self._emit("state_change", self.state)

    def reset(self):
        self._reset()
        self._emit("state_change", self.state)
        self._emit("tick", self.remaining, self.total)

    def skip(self):
        self._advance()

    def tick(self):
        if self.state in ("idle", "paused"):
            return
        self.remaining -= 1
        self._emit("tick", self.remaining, self.total)
        if self.remaining <= 0:
            self._advance()

    def _advance(self):
        if self.state == "working":
            self.session += 1
            if self.session >= 4:
                self.state = "long_break"
                self.session = 0
            else:
                self.state = "short_break"
        else:
            self.state = "working"
        self.remaining = self._total_for_state(self.state)
        self.total = self.remaining
        self.just_advanced = True
        self._emit("state_change", self.state)
        self._emit("tick", self.remaining, self.total)

    def update_config(self, work_mins, short_break_mins, long_break_mins):
        was_idle = self.state == "idle"
        self.work_secs = work_mins * 60
        self.short_break_secs = short_break_mins * 60
        self.long_break_secs = long_break_mins * 60
        if was_idle:
            self._reset()
            self._emit("tick", self.remaining, self.total)

    @property
    def phase_label(self):
        labels = {"idle": "准备就绪", "working": "工作时间",
                  "short_break": "短休息", "long_break": "长休息",
                  "paused": "已暂停"}
        return labels[self.state]

    @property
    def is_running(self):
        return self.state in ("working", "short_break", "long_break")


# ── UI Application ─────────────────────────────────────────────────────

class PomodoroApp:
    COLORS = {
        "working":      ("#e74c3c", "#fef0f0"),
        "short_break":  ("#27ae60", "#eafaf1"),
        "long_break":   ("#2980b9", "#eaf2f8"),
        "idle":         ("#bdc3c7", "#ffffff"),
        "paused":       ("#95a5a6", "#fafafa"),
    }

    def __init__(self):
        self.timer = PomodoroTimer()
        self._tick_job = None
        self._suppress_notify = True
        self._build_ui()
        self._load_config()
        self.timer.on("tick", self._on_tick)
        self.timer.on("state_change", self._on_state_change)
        self._refresh_ui()
        self.root.after(100, self._enable_notify)
        self.root.mainloop()

    def _enable_notify(self):
        self._suppress_notify = False

    # ── config persistence ──────────────────────────────────────────

    def _create_vars(self):
        self._work_var = tk.StringVar(value="25")
        self._short_var = tk.StringVar(value="5")
        self._long_var = tk.StringVar(value="15")

    def _load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            w, s, l = cfg["work"], cfg["short_break"], cfg["long_break"]
            self.timer.update_config(w, s, l)
            self._work_var.set(str(w))
            self._short_var.set(str(s))
            self._long_var.set(str(l))
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass  # keep defaults from _create_vars

    def _save_config(self):
        try:
            w = int(self._work_var.get())
            s = int(self._short_var.get())
            l = int(self._long_var.get())
        except ValueError:
            return
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"work": w, "short_break": s, "long_break": l}, f)
        self.timer.update_config(w, s, l)

    # ── build UI ────────────────────────────────────────────────────

    def _build_ui(self):
        self.root = tk.Tk()
        self._create_vars()
        self.root.title("番茄钟")
        self.root.geometry("340x480")
        self.root.resizable(False, False)
        self.root.configure(bg="#ffffff")

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 340) // 2
        y = (sh - 480) // 2
        self.root.geometry(f"+{x}+{y}")

        ttk.Style(self.root).theme_use("clam")

        # title
        title_lbl = tk.Label(self.root, text="番茄钟",
                             font=("Microsoft YaHei", 20, "bold"),
                             fg="#2c3e50", bg="#ffffff")
        title_lbl.pack(pady=(20, 0))

        self.phase_lbl = tk.Label(self.root, text="",
                                  font=("Microsoft YaHei", 11),
                                  fg="#7f8c8d", bg="#ffffff")
        self.phase_lbl.pack(pady=(2, 8))

        # always-on-top
        self.top_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(self.root, text="窗口置顶", variable=self.top_var,
                             command=self._toggle_topmost)
        cb.pack()

        # canvas with timer text drawn directly on it
        self.canvas = tk.Canvas(self.root, width=220, height=220,
                                bg="#ffffff", highlightthickness=0)
        self.canvas.pack(pady=10)

        # session dots
        self.dots_frame = tk.Frame(self.root, bg="#ffffff")
        self.dots_frame.pack(pady=5)
        self.dot_labels = []
        for _ in range(4):
            lbl = tk.Label(self.dots_frame, text="○", font=("", 20),
                           fg="#d5d8dc", bg="#ffffff")
            lbl.pack(side=tk.LEFT, padx=4)
            self.dot_labels.append(lbl)

        # buttons
        self.btn_frame = tk.Frame(self.root, bg="#ffffff")
        self.btn_frame.pack(pady=12)
        b_opts = {"width": 6, "takefocus": False, "relief": "flat",
                  "font": ("Microsoft YaHei", 10), "fg": "white"}

        self.start_btn = tk.Button(self.btn_frame, text="开始",
                                   command=self._on_start, bg="#27ae60",
                                   activebackground="#2ecc71", **b_opts)
        self.start_btn.pack(side=tk.LEFT, padx=3)

        self.pause_btn = tk.Button(self.btn_frame, text="暂停",
                                   command=self._on_pause, bg="#f39c12",
                                   activebackground="#f1c40f", **b_opts)
        self.pause_btn.pack(side=tk.LEFT, padx=3)

        self.reset_btn = tk.Button(self.btn_frame, text="重置",
                                   command=self._on_reset, bg="#95a5a6",
                                   activebackground="#7f8c8d", **b_opts)
        self.reset_btn.pack(side=tk.LEFT, padx=3)

        self.skip_btn = tk.Button(self.btn_frame, text="跳过",
                                  command=self._on_skip, bg="#3498db",
                                  activebackground="#5dade2", **b_opts)
        self.skip_btn.pack(side=tk.LEFT, padx=3)

        # settings
        sframe = tk.LabelFrame(self.root, text="设置 (分钟)",
                               bg="#ffffff", fg="#7f8c8d",
                               font=("Microsoft YaHei", 9))
        sframe.pack(pady=10, padx=30, fill=tk.X)

        self._make_setting_row(sframe, "工作时间", self._work_var)
        self._make_setting_row(sframe, "短休息", self._short_var)
        self._make_setting_row(sframe, "长休息", self._long_var)

        apply_btn = tk.Button(sframe, text="应用", command=self._apply_settings,
                              bg="#8e44ad", fg="white",
                              font=("Microsoft YaHei", 9),
                              activebackground="#9b59b6", relief="flat")
        apply_btn.pack(pady=8)

    def _make_setting_row(self, parent, text, var):
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(row, text=text, font=("Microsoft YaHei", 9),
                 fg="#7f8c8d", bg="#ffffff", width=8, anchor="w").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=var, width=6, justify="center",
                 font=("Consolas", 10), relief="solid", borderwidth=1).pack(side=tk.RIGHT)

    def _refresh_ui(self):
        """Full refresh: timer text, circle, dots, phase label, colors."""
        self._on_tick(self.timer.remaining, self.timer.total)
        self._on_state_change(self.timer.state)

    def _draw_circle(self, ratio):
        self.canvas.delete("all")
        r, cx, cy = 90, 110, 110
        track_color = "#ecf0f1"
        state_color = self.COLORS.get(self.timer.state, self.COLORS["idle"])[0]

        # background track
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline=track_color, width=10)

        if ratio > 0.001:
            extent = -(ratio * 360.0)
            self.canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                                   start=90, extent=extent,
                                   outline=state_color, width=10, style="arc")
        # timer text centered on canvas
        mins, secs = divmod(self.timer.remaining, 60)
        self.canvas.create_text(cx, cy, text=f"{mins:02d}:{secs:02d}",
                                font=("Consolas", 34, "bold"), fill="#2c3e50")

    def _set_bg_recursive(self, widget, color):
        """Recursively set background color on frames and labels."""
        try:
            if isinstance(widget, (tk.Frame, tk.LabelFrame)):
                widget.configure(bg=color)
            elif isinstance(widget, (tk.Label,)):
                widget.configure(bg=color)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_bg_recursive(child, color)

    def _update_dots(self):
        for i, lbl in enumerate(self.dot_labels):
            if i < self.timer.session:
                lbl.config(text="●", fg="#e74c3c")
            else:
                lbl.config(text="○", fg="#d5d8dc")

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.top_var.get())

    # ── button callbacks ─────────────────────────────────────────────

    def _on_start(self):
        self.timer.start()
        if self.timer.is_running:
            self._start_tick_loop()

    def _on_pause(self):
        if self.timer.state == "paused":
            self.timer.start()
            if self.timer.is_running:
                self._start_tick_loop()
        else:
            self.timer.pause()
            self._stop_tick_loop()

    def _on_reset(self):
        self._stop_tick_loop()
        self.timer.reset()

    def _on_skip(self):
        self._stop_tick_loop()
        self.timer.skip()
        if self.timer.is_running:
            self._start_tick_loop()

    # ── timer callback ───────────────────────────────────────────────

    def _on_tick(self, remaining, total):
        ratio = remaining / total if total > 0 else 1.0
        self._draw_circle(ratio)

    def _on_state_change(self, state):
        color_pair = self.COLORS.get(state, self.COLORS["idle"])
        self._set_bg_recursive(self.root, color_pair[1])
        self.phase_lbl.config(text=self.timer.phase_label, fg=color_pair[0])
        self.start_btn.config(text="继续" if state == "paused" else "开始")
        self._update_dots()
        if not self._suppress_notify and getattr(self.timer, "just_advanced", False):
            self.timer.just_advanced = False
            self._notify()

    def _notify(self):
        try:
            winsound.MessageBeep(0x00000000)
        except Exception:
            pass
        self.root.lift()
        self.root.focus_force()

    # ── tick loop ────────────────────────────────────────────────────

    def _start_tick_loop(self):
        self._stop_tick_loop()
        self._do_tick()

    def _do_tick(self):
        if not self.timer.is_running:
            return
        self.timer.tick()
        self._tick_job = self.root.after(1000, self._do_tick)

    def _stop_tick_loop(self):
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None

    # ── settings ─────────────────────────────────────────────────────

    def _apply_settings(self):
        self._stop_tick_loop()
        self._save_config()
        self.timer.reset()


if __name__ == "__main__":
    PomodoroApp()
