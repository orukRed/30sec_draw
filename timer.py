"""
ドローイングタイマー (常に最前面に表示)

タブで2モードを切替:
- クロッキー: 描画時間 30〜600秒 / インターバル 1〜10秒 / セット数 1〜20
- ワンドロ: 単発の長時間タイマー (60〜180分)。
  「工程モード」を ON にすると、累積分で区切った複数工程
  (例: 構図下書きペン入れ→色塗り→仕上げ) を連続実行し、
  各工程の区切りと完了時に Windows 音で通知する。工程は GUI で追加/削除/編集可。
"""

import sys
import tkinter as tk
from tkinter import ttk, font as tkfont
from enum import Enum
import winsound
import ctypes
import json
from pathlib import Path

# 設定ファイルのパス (実行ファイルと同じディレクトリに保存)
# exe化時は exe の場所、.py 実行時はスクリプトの場所を基準にする
if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent
CONFIG_PATH = _APP_DIR / "config.json"
DEFAULT_CONFIG = {
    "mode": "croquis",
    "croquis": {"draw_time": 90, "interval": 5, "sets": 10},
    "wandoro": {
        "draw_time_min": 60,
        "stages_enabled": False,
        "stages": [
            {"label": "構図下書きペン入れ", "at_min": 30},
            {"label": "色塗り", "at_min": 50},
            {"label": "仕上げ", "at_min": 60},
        ],
    },
}

# 工程の分指定の範囲・刻み
STAGE_MIN = 1
STAGE_MAX = 600
STAGE_STEP = 5

# 高DPI対応 (Per Monitor DPI Aware)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class Phase(Enum):
    IDLE = "待機中"
    DRAWING = "描画中"
    INTERVAL = "インターバル"
    PAUSED = "一時停止中"


class Mode(Enum):
    CROQUIS = "croquis"   # クロッキー (短時間 × 複数セット + インターバル)
    WANDORO = "wandoro"   # ワンドロ (単発の長時間タイマー)


class DrawingTimer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("30秒ドローイングタイマー")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")

        # 状態変数
        self.phase = Phase.IDLE
        self.paused_phase: Phase | None = None  # 一時停止前のフェーズ
        self.remaining = 0  # 残り秒数
        self.current_set = 0
        self.total_sets = 0
        self.after_id: str | None = None

        # ワンドロ工程モードの実行時状態
        self.is_staged = False              # 現在の実行が工程モードか
        self.stage_durations: list[int] = []  # 各工程の長さ(秒)
        self.stage_labels: list[str] = []     # 各工程のラベル

        # 保存済み設定の読み込み
        config = self._load_config()

        # 現在のモード
        self.mode = Mode(config["mode"])

        # tkinter 変数 (クロッキー用)
        self.draw_time_var = tk.IntVar(value=config["croquis"]["draw_time"])
        self.interval_var = tk.IntVar(value=config["croquis"]["interval"])
        self.sets_var = tk.IntVar(value=config["croquis"]["sets"])
        # tkinter 変数 (ワンドロ用: 描画時間 分単位)
        self.wandoro_min_var = tk.IntVar(value=config["wandoro"]["draw_time_min"])
        # ワンドロ工程モードの ON/OFF
        self.wandoro_enabled_var = tk.BooleanVar(
            value=config["wandoro"]["stages_enabled"]
        )
        # 工程の編集用変数 (ラベル, 累積分) のリスト
        self.wandoro_stage_vars: list[tuple[tk.StringVar, tk.IntVar]] = []
        for stage in config["wandoro"]["stages"]:
            self._make_stage_var(stage["label"], stage["at_min"])

        # 設定変更時に自動保存
        self.draw_time_var.trace_add("write", lambda *_: self._save_config())
        self.interval_var.trace_add("write", lambda *_: self._save_config())
        self.sets_var.trace_add("write", lambda *_: self._save_config())
        self.wandoro_min_var.trace_add("write", lambda *_: self._save_config())
        self.wandoro_enabled_var.trace_add("write", lambda *_: self._save_config())

        self._build_ui()
        self._update_button_states()

        # ウィンドウ閉じ時のクリーンアップ
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ──────────────────────────────────────
    #  UI構築
    # ──────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # --- 色定義 ---
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ACCENT = "#89b4fa"
        SURFACE = "#313244"

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TButton", padding=6)
        style.configure(
            "TSpinbox",
            fieldbackground=SURFACE,
            foreground=FG,
            background=SURFACE,
        )

        # ─── スピナーボタン用スタイル ───
        spin_btn_font = tkfont.Font(family="Yu Gothic UI", size=14, weight="bold")
        style.configure(
            "Spin.TButton",
            font=spin_btn_font,
            padding=(12, 4),
        )
        val_font = tkfont.Font(family="Consolas", size=14)
        # 工程エディタの動的生成で再利用するため保持
        self._val_font = val_font
        self._FG, self._BG, self._SURFACE = FG, BG, SURFACE

        # ─── タブ(モード切替)用スタイル ───
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=SURFACE,
            foreground=FG,
            padding=(16, 6),
            font=tkfont.Font(family="Yu Gothic UI", size=11),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT)],
            foreground=[("selected", BG)],
        )

        # ─── 設定パネル (タブでモード切替) ───
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="x", padx=15, pady=(15, 0))

        croquis_frame = ttk.Frame(self.notebook, padding=15)
        wandoro_frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(croquis_frame, text="クロッキー")
        self.notebook.add(wandoro_frame, text="ワンドロ")

        # 値変更用ボタン群を作るヘルパー
        self._setting_btns: list[tuple[ttk.Button, ttk.Button]] = []

        def make_spinner_row(parent, label_text, var, vmin, vmax, step, fmt=str):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label_text, width=16, anchor="e").pack(
                side="left", padx=(0, 8)
            )
            val_lbl = tk.Label(
                row, textvariable=var, font=val_font,
                width=6, anchor="center", fg=FG, bg=SURFACE,
                relief="flat", padx=4, pady=2,
            )
            btn_minus = ttk.Button(
                row, text="−", style="Spin.TButton", width=3,
                command=lambda: var.set(max(vmin, var.get() - step)),
            )
            btn_plus = ttk.Button(
                row, text="＋", style="Spin.TButton", width=3,
                command=lambda: var.set(min(vmax, var.get() + step)),
            )
            btn_minus.pack(side="left", padx=(0, 4))
            val_lbl.pack(side="left", padx=2)
            btn_plus.pack(side="left", padx=(4, 0))
            self._setting_btns.append((btn_minus, btn_plus))
            return row

        # ─── クロッキータブ ───
        # 描画時間
        make_spinner_row(croquis_frame, "描画時間 (秒):",
                         self.draw_time_var, 30, 600, 30)
        # インターバル
        make_spinner_row(croquis_frame, "インターバル (秒):",
                         self.interval_var, 1, 10, 1)
        # セット数
        make_spinner_row(croquis_frame, "セット数:",
                         self.sets_var, 1, 20, 1)

        # ─── ワンドロタブ ───
        # 工程モード ON/OFF トグル
        self.wandoro_toggle = ttk.Checkbutton(
            wandoro_frame, text="工程モードを使う",
            variable=self.wandoro_enabled_var,
            command=self._on_wandoro_toggle,
        )
        self.wandoro_toggle.pack(anchor="w", pady=(0, 8))

        # 単一タイマー用フレーム (工程OFF時): 描画時間 (分)
        self.wandoro_single_frame = ttk.Frame(wandoro_frame)
        make_spinner_row(self.wandoro_single_frame, "描画時間 (分):",
                         self.wandoro_min_var, 60, 180, 10)

        # 工程エディタ用フレーム (工程ON時)
        self.wandoro_staged_frame = ttk.Frame(wandoro_frame)
        hdr = ttk.Frame(self.wandoro_staged_frame)
        hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(hdr, text="工程名", width=18, anchor="w").pack(
            side="left", padx=(0, 4)
        )
        ttk.Label(hdr, text="終了(分)", anchor="w").pack(side="left")
        # 各工程行を入れるコンテナ
        self.wandoro_rows_container = ttk.Frame(self.wandoro_staged_frame)
        self.wandoro_rows_container.pack(fill="x")
        # 工程を追加するボタン
        self.wandoro_add_btn = ttk.Button(
            self.wandoro_staged_frame, text="＋ 工程を追加",
            command=self._add_stage_clicked,
        )
        self.wandoro_add_btn.pack(anchor="w", pady=(6, 0))

        # 工程行を描画し、トグルに応じて表示するフレームを切替
        self._wandoro_edit_widgets: list = []
        self._render_stages()
        if self.wandoro_enabled_var.get():
            self.wandoro_staged_frame.pack(fill="x")
        else:
            self.wandoro_single_frame.pack(fill="x")

        # 起動時のモードに合わせてタブを選択
        self.notebook.select(
            1 if self.mode == Mode.WANDORO else 0
        )
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ─── セパレータ ───
        sep = tk.Frame(self.root, height=1, bg="#45475a")
        sep.pack(fill="x", padx=15)

        # ─── カウントダウン表示 ───
        display_frame = ttk.Frame(self.root, padding=(15, 20))
        display_frame.pack(fill="both", expand=True)

        self.time_font = tkfont.Font(family="Consolas", size=72, weight="bold")
        self.time_label = tk.Label(
            display_frame,
            text="00:00",
            font=self.time_font,
            fg="#a6adc8",
            bg=BG,
        )
        self.time_label.pack()

        self.status_font = tkfont.Font(family="Yu Gothic UI", size=14)
        self.status_label = tk.Label(
            display_frame,
            text="待機中",
            font=self.status_font,
            fg="#a6adc8",
            bg=BG,
        )
        self.status_label.pack(pady=(5, 0))

        # ─── セパレータ ───
        sep2 = tk.Frame(self.root, height=1, bg="#45475a")
        sep2.pack(fill="x", padx=15)

        # ─── コントロールボタン ───
        btn_frame = ttk.Frame(self.root, padding=15)
        btn_frame.pack(fill="x")

        self.btn_start = ttk.Button(
            btn_frame, text="▶ 開始", command=self._start, width=10
        )
        self.btn_start.pack(side="left", padx=3, expand=True)

        self.btn_pause = ttk.Button(
            btn_frame, text="⏸ 一時停止", command=self._toggle_pause, width=12
        )
        self.btn_pause.pack(side="left", padx=3, expand=True)

        self.btn_skip = ttk.Button(
            btn_frame, text="⏭ スキップ", command=self._skip, width=12
        )
        self.btn_skip.pack(side="left", padx=3, expand=True)

        self.btn_stop = ttk.Button(
            btn_frame, text="⏹ 停止", command=self._stop, width=10
        )
        self.btn_stop.pack(side="left", padx=3, expand=True)

    # ──────────────────────────────────────
    #  モード切替
    # ──────────────────────────────────────
    def _on_tab_changed(self, event=None):
        """タブ切替時にモードを更新。動作中は切替を拒否して元へ戻す。"""
        selected = self.notebook.index(self.notebook.select())
        new_mode = Mode.WANDORO if selected == 1 else Mode.CROQUIS

        # 待機中以外はモード変更不可 → 現在のモードのタブへ戻す
        if self.phase != Phase.IDLE and new_mode != self.mode:
            self.notebook.select(1 if self.mode == Mode.WANDORO else 0)
            return

        self.mode = new_mode
        self._save_config()
        self._update_display()

    # ──────────────────────────────────────
    #  ワンドロ工程エディタ
    # ──────────────────────────────────────
    def _make_stage_var(self, label: str, at_min: int):
        """工程1件分の (ラベル, 累積分) 変数を作成しリストへ追加。"""
        label_var = tk.StringVar(value=str(label))
        min_var = tk.IntVar(value=int(at_min))
        label_var.trace_add("write", lambda *_: self._save_config())
        min_var.trace_add("write", lambda *_: self._save_config())
        self.wandoro_stage_vars.append((label_var, min_var))
        return label_var, min_var

    def _render_stages(self):
        """wandoro_stage_vars の内容から工程行を作り直す。"""
        cont = self.wandoro_rows_container
        for child in cont.winfo_children():
            child.destroy()
        self._wandoro_edit_widgets = []

        for idx, (label_var, min_var) in enumerate(self.wandoro_stage_vars):
            row = ttk.Frame(cont)
            row.pack(fill="x", pady=2)
            entry = ttk.Entry(row, textvariable=label_var, width=18)
            entry.pack(side="left", padx=(0, 4))
            btn_minus = ttk.Button(
                row, text="−", style="Spin.TButton", width=2,
                command=lambda v=min_var: v.set(
                    max(STAGE_MIN, v.get() - STAGE_STEP)),
            )
            val_lbl = tk.Label(
                row, textvariable=min_var, font=self._val_font,
                width=4, anchor="center", fg=self._FG, bg=self._SURFACE,
                relief="flat", padx=2, pady=2,
            )
            btn_plus = ttk.Button(
                row, text="＋", style="Spin.TButton", width=2,
                command=lambda v=min_var: v.set(
                    min(STAGE_MAX, v.get() + STAGE_STEP)),
            )
            btn_del = ttk.Button(
                row, text="×", style="Spin.TButton", width=2,
                command=lambda i=idx: self._remove_stage(i),
            )
            btn_minus.pack(side="left", padx=(0, 2))
            val_lbl.pack(side="left", padx=2)
            btn_plus.pack(side="left", padx=(2, 6))
            btn_del.pack(side="left")
            self._wandoro_edit_widgets += [entry, btn_minus, btn_plus, btn_del]

        # 動作中なら新規行も無効状態に合わせる
        self._set_wandoro_edit_state(self.phase == Phase.IDLE)

    def _add_stage_clicked(self):
        """工程を1件追加する。"""
        last = self.wandoro_stage_vars[-1][1].get() if self.wandoro_stage_vars else 0
        at_min = min(STAGE_MAX, last + STAGE_STEP * 2)
        self._make_stage_var("", at_min)
        self._render_stages()
        self._save_config()

    def _remove_stage(self, index: int):
        """指定インデックスの工程を削除する。"""
        if 0 <= index < len(self.wandoro_stage_vars):
            del self.wandoro_stage_vars[index]
            self._render_stages()
            self._save_config()

    def _on_wandoro_toggle(self):
        """工程モード ON/OFF で単一/工程フレームを切替える。"""
        if self.wandoro_enabled_var.get():
            self.wandoro_single_frame.pack_forget()
            self.wandoro_staged_frame.pack(fill="x")
        else:
            self.wandoro_staged_frame.pack_forget()
            self.wandoro_single_frame.pack(fill="x")
        self._save_config()

    def _set_wandoro_edit_state(self, enabled: bool):
        """工程エディタ(トグル・追加・各行)の有効/無効を切替える。"""
        state = "normal" if enabled else "disabled"
        for w in (self.wandoro_toggle, self.wandoro_add_btn):
            try:
                w.config(state=state)
            except tk.TclError:
                pass
        for w in self._wandoro_edit_widgets:
            try:
                w.config(state=state)
            except tk.TclError:
                pass

    def _build_stage_plan(self):
        """工程変数から (各工程の長さ[秒], ラベル) を構築する。

        累積分(at_min)を昇順・狭義単調増加に正規化し、区間長へ変換する。
        有効な工程が無ければ ([], []) を返す。
        """
        stages = []
        for label_var, min_var in self.wandoro_stage_vars:
            try:
                at = int(min_var.get())
            except (tk.TclError, ValueError):
                continue
            if at < STAGE_MIN or at > STAGE_MAX:
                continue
            stages.append((label_var.get().strip(), at))
        stages.sort(key=lambda s: s[1])

        durations, labels = [], []
        prev = 0
        for label, at in stages:
            if at <= prev:
                continue  # 単調増加でなければスキップ
            durations.append((at - prev) * 60)
            labels.append(label or f"工程{len(labels) + 1}")
            prev = at
        return durations, labels

    # ──────────────────────────────────────
    #  表示更新
    # ──────────────────────────────────────
    def _format_time(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def _update_display(self):
        self.time_label.config(text=self._format_time(self.remaining))

        if self.phase == Phase.DRAWING:
            self.time_label.config(fg="#f38ba8")  # 赤系
            if self.is_staged:
                label = self.stage_labels[self.current_set - 1]
                text = f"🖊 {label} （{self.current_set}/{self.total_sets}）"
            elif self.mode == Mode.WANDORO:
                text = "🖊 描画中"
            else:
                text = f"🖊 描画中 — セット {self.current_set}/{self.total_sets}"
            self.status_label.config(text=text, fg="#f38ba8")
        elif self.phase == Phase.INTERVAL:
            self.time_label.config(fg="#89b4fa")  # 青系
            self.status_label.config(
                text=f"☕ インターバル — セット {self.current_set}/{self.total_sets}",
                fg="#89b4fa",
            )
        elif self.phase == Phase.PAUSED:
            self.time_label.config(fg="#fab387")  # オレンジ系
            if self.is_staged:
                label = self.stage_labels[self.current_set - 1]
                text = f"⏸ 一時停止中 — {label}"
            elif self.mode == Mode.WANDORO:
                text = "⏸ 一時停止中"
            else:
                text = f"⏸ 一時停止中 — セット {self.current_set}/{self.total_sets}"
            self.status_label.config(text=text, fg="#fab387")
        else:
            self.time_label.config(text="00:00", fg="#a6adc8")
            self.status_label.config(text="待機中", fg="#a6adc8")

    def _update_button_states(self):
        is_idle = self.phase == Phase.IDLE
        is_running = self.phase in (Phase.DRAWING, Phase.INTERVAL)
        is_paused = self.phase == Phase.PAUSED

        # 開始ボタン: IDLEの時だけ有効
        self.btn_start.config(state="normal" if is_idle else "disabled")

        # 一時停止ボタン: 動作中/一時停止中のみ有効
        if is_running:
            self.btn_pause.config(state="normal", text="⏸ 一時停止")
        elif is_paused:
            self.btn_pause.config(state="normal", text="▶ 再開")
        else:
            self.btn_pause.config(state="disabled", text="⏸ 一時停止")

        # スキップ/停止: 動作中/一時停止中のみ有効
        active_state = "normal" if (is_running or is_paused) else "disabled"
        self.btn_skip.config(state=active_state)
        self.btn_stop.config(state=active_state)

        # 設定ボタン: IDLEの時だけ変更可能
        btn_state = "normal" if is_idle else "disabled"
        for btn_minus, btn_plus in self._setting_btns:
            btn_minus.config(state=btn_state)
            btn_plus.config(state=btn_state)

        # ワンドロ工程エディタも IDLE のときだけ編集可能
        self._set_wandoro_edit_state(is_idle)

    # ──────────────────────────────────────
    #  タイマーロジック
    # ──────────────────────────────────────
    def _tick(self):
        """1秒ごとに呼ばれるカウントダウン処理"""
        if self.phase not in (Phase.DRAWING, Phase.INTERVAL):
            return

        self.remaining -= 1
        self._update_display()

        if self.remaining <= 0:
            self._on_phase_end()
        else:
            self.after_id = self.root.after(1000, self._tick)

    def _on_phase_end(self):
        """フェーズ(描画/インターバル)が終了した時の処理"""
        if self.phase == Phase.DRAWING:
            # 描画時間が終了 → 音を鳴らす
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

            if self.current_set >= self.total_sets:
                # 全セット完了
                self._on_all_complete()
                return

            if self.is_staged:
                # 工程モード: インターバルを挟まず次工程へ
                self.current_set += 1
                self.remaining = self.stage_durations[self.current_set - 1]
                # phase は DRAWING のまま
                self._update_display()
                self._update_button_states()
                self.after_id = self.root.after(1000, self._tick)
                return

            # インターバルフェーズへ移行
            self.phase = Phase.INTERVAL
            self.remaining = self.interval_var.get()
            self._update_display()
            self._update_button_states()
            self.after_id = self.root.after(1000, self._tick)

        elif self.phase == Phase.INTERVAL:
            # インターバル終了 → 音を鳴らして次のセットの描画フェーズへ
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            self.current_set += 1
            self.phase = Phase.DRAWING
            self.remaining = self.draw_time_var.get()
            self._update_display()
            self._update_button_states()
            self.after_id = self.root.after(1000, self._tick)

    def _on_all_complete(self):
        """全セット完了時の処理"""
        # 目立つ音で完了通知
        winsound.MessageBeep(winsound.MB_ICONHAND)
        self.phase = Phase.IDLE
        self.time_label.config(text="完了!", fg="#a6e3a1")
        if self.mode == Mode.WANDORO:
            complete_text = "✅ 完了"
        else:
            complete_text = f"✅ 全{self.total_sets}セット完了"
        self.status_label.config(text=complete_text, fg="#a6e3a1")
        self._update_button_states()

    # ──────────────────────────────────────
    #  ボタンイベント
    # ──────────────────────────────────────
    def _start(self):
        """タイマーを開始"""
        if self.mode == Mode.WANDORO:
            durations, labels = self._build_stage_plan()
            if self.wandoro_enabled_var.get() and durations:
                # ワンドロ工程モード: 複数工程を連続実行 (インターバルなし)
                self.is_staged = True
                self.stage_durations = durations
                self.stage_labels = labels
                self.total_sets = len(durations)
                self.remaining = durations[0]
            else:
                # ワンドロ単発タイマー (1セット・インターバルなし)
                self.is_staged = False
                self.total_sets = 1
                self.remaining = self.wandoro_min_var.get() * 60
        else:
            # クロッキー: 複数セット + インターバル
            self.is_staged = False
            self.total_sets = self.sets_var.get()
            self.remaining = self.draw_time_var.get()
        self.current_set = 1
        self.phase = Phase.DRAWING
        self.paused_phase = None

        self._update_display()
        self._update_button_states()
        self.after_id = self.root.after(1000, self._tick)

    def _toggle_pause(self):
        """一時停止 / 再開"""
        if self.phase in (Phase.DRAWING, Phase.INTERVAL):
            # 一時停止
            self.paused_phase = self.phase
            self.phase = Phase.PAUSED
            if self.after_id is not None:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            self._update_display()
            self._update_button_states()

        elif self.phase == Phase.PAUSED:
            # 再開
            self.phase = self.paused_phase or Phase.DRAWING
            self.paused_phase = None
            self._update_display()
            self._update_button_states()
            self.after_id = self.root.after(1000, self._tick)

    def _skip(self):
        """現在のフェーズをスキップして次へ"""
        # 進行中のタイマーをキャンセル
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        # 一時停止中の場合はフェーズを復元
        active_phase = (
            self.paused_phase if self.phase == Phase.PAUSED else self.phase
        )
        self.paused_phase = None

        if active_phase == Phase.DRAWING:
            # 描画フェーズをスキップ → 最終セットなら完了、それ以外は次へ
            if self.current_set >= self.total_sets:
                self._on_all_complete()
                return
            if self.is_staged:
                # 工程モード: 次工程の描画へ (インターバルなし)
                self.current_set += 1
                self.remaining = self.stage_durations[self.current_set - 1]
                # phase は DRAWING のまま
            else:
                self.phase = Phase.INTERVAL
                self.remaining = self.interval_var.get()

        elif active_phase == Phase.INTERVAL:
            # インターバルをスキップ → 次の描画セットへ
            self.current_set += 1
            self.phase = Phase.DRAWING
            self.remaining = self.draw_time_var.get()

        self._update_display()
        self._update_button_states()
        self.after_id = self.root.after(1000, self._tick)

    def _stop(self):
        """タイマーを停止してリセット"""
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        self.phase = Phase.IDLE
        self.paused_phase = None
        self.remaining = 0
        self.current_set = 0
        self.is_staged = False
        self._update_display()
        self._update_button_states()

    # ──────────────────────────────────────
    #  設定の保存・読み込み
    # ──────────────────────────────────────
    @staticmethod
    def _load_config() -> dict:
        """config.json から設定を読み込む。なければデフォルト値を返す。

        モード別の新形式と、旧フラット形式 (draw_time/interval/sets が
        トップレベル) の両方を読めるよう後方互換を持たせている。
        """
        defaults = DEFAULT_CONFIG
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError

            # クロッキー設定: 新形式は data["croquis"]、旧形式はトップレベル
            cq = data.get("croquis", data)
            dt = int(cq.get("draw_time", defaults["croquis"]["draw_time"]))
            iv = int(cq.get("interval", defaults["croquis"]["interval"]))
            st = int(cq.get("sets", defaults["croquis"]["sets"]))
            # 範囲内にクランプ & 刻みに合わせる
            dt = max(30, min(600, (dt // 30) * 30))
            iv = max(1, min(10, iv))
            st = max(1, min(20, st))

            # ワンドロ設定 (分単位、60〜180、10刻み)
            wd = data.get("wandoro", {})
            if not isinstance(wd, dict):
                wd = {}
            wm = int(wd.get("draw_time_min", defaults["wandoro"]["draw_time_min"]))
            wm = max(60, min(180, round(wm / 10) * 10))

            # ワンドロ工程設定
            stages_enabled = bool(
                wd.get("stages_enabled", defaults["wandoro"]["stages_enabled"])
            )
            stages = []
            for s in wd.get("stages", []) or []:
                if not isinstance(s, dict):
                    continue
                try:
                    at = int(s.get("at_min"))
                except (TypeError, ValueError):
                    continue
                at = max(STAGE_MIN, min(STAGE_MAX, at))
                stages.append({"label": str(s.get("label", "")), "at_min": at})
            if not stages:
                stages = [dict(x) for x in defaults["wandoro"]["stages"]]

            # モード文字列 (無効なら croquis)
            mode = data.get("mode", "croquis")
            if mode not in (m.value for m in Mode):
                mode = "croquis"

            return {
                "mode": mode,
                "croquis": {"draw_time": dt, "interval": iv, "sets": st},
                "wandoro": {
                    "draw_time_min": wm,
                    "stages_enabled": stages_enabled,
                    "stages": stages,
                },
            }
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
            return json.loads(json.dumps(defaults))  # ディープコピー

    def _save_config(self):
        """現在の設定値を config.json に保存する。"""
        try:
            config = {
                "mode": self.mode.value,
                "croquis": {
                    "draw_time": self.draw_time_var.get(),
                    "interval": self.interval_var.get(),
                    "sets": self.sets_var.get(),
                },
                "wandoro": {
                    "draw_time_min": self.wandoro_min_var.get(),
                    "stages_enabled": self.wandoro_enabled_var.get(),
                    "stages": [
                        {"label": label_var.get(), "at_min": min_var.get()}
                        for label_var, min_var in self.wandoro_stage_vars
                    ],
                },
            }
            CONFIG_PATH.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # 保存失敗は無視（読み取り専用環境など）

    def _on_closing(self):
        """ウィンドウ閉じ時のクリーンアップ"""
        self._save_config()
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    root.configure(bg="#1e1e2e")

    # アイコン設定 (exe化時はバンドル内 or exe横、.py実行時はスクリプト横)
    if getattr(sys, 'frozen', False):
        icon_path = Path(getattr(sys, '_MEIPASS', '')) / "icon.ico"
        if not icon_path.exists():
            icon_path = _APP_DIR / "icon.ico"
    else:
        icon_path = _APP_DIR / "icon.ico"
    if icon_path.exists():
        root.iconbitmap(str(icon_path))

    DrawingTimer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
