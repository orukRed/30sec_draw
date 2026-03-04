"""
30秒ドローイングタイマー
- 常に最前面に表示
- 描画時間: 30秒～300秒 (30秒刻み)
- インターバル: 1秒～10秒 (1秒刻み)
- セット数: 1～20
- 描画時間終了時にWindows音で通知
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
from enum import Enum
import winsound
import ctypes
import json
from pathlib import Path

# 設定ファイルのパス (スクリプトと同じディレクトリに保存)
CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {"draw_time": 30, "interval": 5, "sets": 10}

# 高DPI対応
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class Phase(Enum):
    IDLE = "待機中"
    DRAWING = "描画中"
    INTERVAL = "インターバル"
    PAUSED = "一時停止中"


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

        # 保存済み設定の読み込み
        config = self._load_config()

        # tkinter 変数
        self.draw_time_var = tk.IntVar(value=config["draw_time"])
        self.interval_var = tk.IntVar(value=config["interval"])
        self.sets_var = tk.IntVar(value=config["sets"])

        # 設定変更時に自動保存
        self.draw_time_var.trace_add("write", lambda *_: self._save_config())
        self.interval_var.trace_add("write", lambda *_: self._save_config())
        self.sets_var.trace_add("write", lambda *_: self._save_config())

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

        # ─── 設定パネル ───
        settings_frame = ttk.Frame(self.root, padding=15)
        settings_frame.pack(fill="x")

        # 描画時間
        row = ttk.Frame(settings_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="描画時間 (秒):", width=16, anchor="e").pack(
            side="left", padx=(0, 8)
        )
        self.draw_spin = ttk.Spinbox(
            row,
            from_=30,
            to=300,
            increment=30,
            textvariable=self.draw_time_var,
            width=8,
            state="readonly",
        )
        self.draw_spin.pack(side="left")

        # インターバル
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=3)
        ttk.Label(row2, text="インターバル (秒):", width=16, anchor="e").pack(
            side="left", padx=(0, 8)
        )
        self.interval_spin = ttk.Spinbox(
            row2,
            from_=1,
            to=10,
            increment=1,
            textvariable=self.interval_var,
            width=8,
            state="readonly",
        )
        self.interval_spin.pack(side="left")

        # セット数
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=3)
        ttk.Label(row3, text="セット数:", width=16, anchor="e").pack(
            side="left", padx=(0, 8)
        )
        self.sets_spin = ttk.Spinbox(
            row3,
            from_=1,
            to=20,
            increment=1,
            textvariable=self.sets_var,
            width=8,
            state="readonly",
        )
        self.sets_spin.pack(side="left")

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
    #  表示更新
    # ──────────────────────────────────────
    def _format_time(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def _update_display(self):
        self.time_label.config(text=self._format_time(self.remaining))

        if self.phase == Phase.DRAWING:
            self.time_label.config(fg="#f38ba8")  # 赤系
            self.status_label.config(
                text=f"🖊 描画中 — セット {self.current_set}/{self.total_sets}",
                fg="#f38ba8",
            )
        elif self.phase == Phase.INTERVAL:
            self.time_label.config(fg="#89b4fa")  # 青系
            self.status_label.config(
                text=f"☕ インターバル — セット {self.current_set}/{self.total_sets}",
                fg="#89b4fa",
            )
        elif self.phase == Phase.PAUSED:
            self.time_label.config(fg="#fab387")  # オレンジ系
            self.status_label.config(
                text=f"⏸ 一時停止中 — セット {self.current_set}/{self.total_sets}",
                fg="#fab387",
            )
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

        # Spinbox: IDLEの時だけ変更可能
        spin_state = "readonly" if is_idle else "disabled"
        self.draw_spin.config(state=spin_state)
        self.interval_spin.config(state=spin_state)
        self.sets_spin.config(state=spin_state)

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

            # インターバルフェーズへ移行
            self.phase = Phase.INTERVAL
            self.remaining = self.interval_var.get()
            self._update_display()
            self._update_button_states()
            self.after_id = self.root.after(1000, self._tick)

        elif self.phase == Phase.INTERVAL:
            # インターバル終了 → 次のセットの描画フェーズへ
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
        self.status_label.config(
            text=f"✅ 全{self.total_sets}セット完了", fg="#a6e3a1"
        )
        self._update_button_states()

    # ──────────────────────────────────────
    #  ボタンイベント
    # ──────────────────────────────────────
    def _start(self):
        """タイマーを開始"""
        self.total_sets = self.sets_var.get()
        self.current_set = 1
        self.remaining = self.draw_time_var.get()
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
            # 描画フェーズをスキップ → 最終セットなら完了、それ以外はインターバルへ
            if self.current_set >= self.total_sets:
                self._on_all_complete()
                return
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
        self._update_display()
        self._update_button_states()

    # ──────────────────────────────────────
    #  設定の保存・読み込み
    # ──────────────────────────────────────
    @staticmethod
    def _load_config() -> dict:
        """config.json から設定を読み込む。なければデフォルト値を返す。"""
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # 値のバリデーション
            dt = int(data.get("draw_time", 30))
            iv = int(data.get("interval", 5))
            st = int(data.get("sets", 10))
            # 範囲内にクランプ & 刻みに合わせる
            dt = max(30, min(300, (dt // 30) * 30))
            iv = max(1, min(10, iv))
            st = max(1, min(20, st))
            return {"draw_time": dt, "interval": iv, "sets": st}
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
            return dict(DEFAULT_CONFIG)

    def _save_config(self):
        """現在の設定値を config.json に保存する。"""
        try:
            config = {
                "draw_time": self.draw_time_var.get(),
                "interval": self.interval_var.get(),
                "sets": self.sets_var.get(),
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
    DrawingTimer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
