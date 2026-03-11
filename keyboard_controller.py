"""
AIVtuber — keyboard_controller.py
キーボードショートカットコントローラー

【ショートカット一覧】
  感情手動設定:
    F1  → 喜び (joy)
    F2  → 怒り (anger)
    F3  → 悲しみ (sadness)
    F4  → 驚き (surprise)
    F5  → 照れ (shy)
    F6  → テンション (excited)
    F7  → だるい (bored)
    F8  → ニュートラル

  特殊アクション:
    F9  → 革新トリガー（話題転換を強制）
    F10 → 笑い（コメント返し）
    F11 → 「ちょっと待って」（一時停止感）
    F12 → エネルギー回復

  テンション:
    + → テンションUP
    - → テンションDOWN

    Ctrl+R → キャラ設定リロード
    Ctrl+S → 現在の状態を保存
    ESC    → 終了確認
"""

import asyncio, threading
from typing import Callable


SHORTCUTS = {
    "f1":  ("emotion", "joy",      0.85),
    "f2":  ("emotion", "anger",    0.85),
    "f3":  ("emotion", "sadness",  0.85),
    "f4":  ("emotion", "surprise", 0.95),
    "f5":  ("emotion", "shy",      0.85),
    "f6":  ("emotion", "excited",  0.90),
    "f7":  ("emotion", "bored",    0.80),
    "f8":  ("emotion", "neutral",  0.90),
    "f9":  ("action",  "tangent",  None),
    "f10": ("action",  "laugh",    None),
    "f11": ("action",  "pause",    None),
    "f12": ("action",  "recharge", None),
    "+":   ("tension", "up",       None),
    "-":   ("tension", "down",     None),
}


class KeyboardController:
    def __init__(self, emotion_engine, comment_processor=None):
        self._emotion    = emotion_engine
        self._processor  = comment_processor
        self._running    = False
        self._callbacks: list[Callable] = []
        self._thread     = None

    def add_callback(self, fn: Callable):
        """キー入力時に呼ぶコールバックを追加"""
        self._callbacks.append(fn)

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True)
        self._thread.start()
        print("[keyboard] ショートカット監視開始")
        self._print_help()

    def stop(self):
        self._running = False

    def _loop(self):
        try:
            import keyboard
            for key, action in SHORTCUTS.items():
                # クロージャのためにデフォルト引数でキャプチャ
                def make_handler(a=action):
                    def handler():
                        self._handle(a)
                    return handler
                keyboard.add_hotkey(key, make_handler())
            keyboard.wait()
        except ImportError:
            print("[keyboard] keyboardライブラリ未インストール")
            print("  pip install keyboard  でインストールできます")
            print("[keyboard] フォールバック: 標準入力モードで起動")
            self._stdin_loop()

    def _stdin_loop(self):
        """keyboardライブラリなし時のフォールバック（標準入力）"""
        print("\n[keyboard] コマンド入力モード")
        print("  j=喜び a=怒り s=悲しみ u=驚き h=照れ e=テンション b=だるい n=普通")
        print("  t=革新 +=テンションUP -=テンションDOWN q=終了\n")
        while self._running:
            try:
                cmd = input("> ").strip().lower()
                cmd_map = {
                    "j": ("emotion", "joy",      0.85),
                    "a": ("emotion", "anger",    0.85),
                    "s": ("emotion", "sadness",  0.85),
                    "u": ("emotion", "surprise", 0.95),
                    "h": ("emotion", "shy",      0.85),
                    "e": ("emotion", "excited",  0.90),
                    "b": ("emotion", "bored",    0.80),
                    "n": ("emotion", "neutral",  0.90),
                    "t": ("action",  "tangent",  None),
                    "+": ("tension", "up",       None),
                    "-": ("tension", "down",     None),
                }
                if cmd in cmd_map:
                    self._handle(cmd_map[cmd])
                elif cmd == "q":
                    self._running = False
                    break
            except (EOFError, KeyboardInterrupt):
                break

    def _handle(self, action: tuple):
        kind, name, value = action

        if kind == "emotion":
            self._emotion.manual_override(name, value)
            print(f"[keyboard] 感情セット: {name}")

        elif kind == "action":
            if name == "tangent":
                # 革新を強制発動
                self._emotion._tangent_counter = 999
                print("[keyboard] 革新トリガー発動")
            elif name == "laugh":
                self._emotion.manual_override("joy", 0.9)
                self._emotion.manual_override("excited", 0.7)
            elif name == "pause":
                self._emotion.manual_override("neutral", 0.8)
                print("[keyboard] 一時停止感")
            elif name == "recharge":
                self._emotion.state.energy = min(1.0,
                    self._emotion.state.energy + 0.3)
                print(f"[keyboard] エネルギー回復: {self._emotion.state.energy:.1f}")

        elif kind == "tension":
            delta = 0.15 if name == "up" else -0.15
            self._emotion.state.tension = max(0.1, min(1.0,
                self._emotion.state.tension + delta))
            print(f"[keyboard] テンション: {self._emotion.state.tension:.1f}")

        # コールバック通知
        state = self._emotion.get_current_state()
        for cb in self._callbacks:
            try:
                cb(state)
            except Exception:
                pass

    def _print_help(self):
        print("\n" + "="*50)
        print("  AIVtuber キーボードショートカット")
        print("="*50)
        print("  F1-F8: 感情手動設定")
        print("  F9:    革新（話題転換）")
        print("  F10:   笑い")
        print("  F12:   エネルギー回復")
        print("  +/-:   テンション調整")
        print("="*50 + "\n")
