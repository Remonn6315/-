"""
Blackwell Dev-OS — pair_programmer.py v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AIペアプログラマーモード（対話型開発）

従来の「指示→完成コード」の一発生成ではなく、
「設計確認→承認→実装→レビュー→修正」の
Cursor的な対話型フローで開発する。

フロー:
  PHASE_DESIGN   : 実装方針をAIが提案 → ユーザーが承認/修正
  PHASE_IMPLEMENT: 承認された方針でコード生成
  PHASE_REVIEW   : AIが自分のコードをレビュー
  PHASE_REFINE   : レビュー指摘を自動修正
  PHASE_DONE     : 完成

【公開API】
  PairSession.start(goal, anchor, save_path) → PairSession
  PairSession.respond(user_input)            → PairResponse
  PairSession.get_state()                    → dict
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ollama
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# フェーズ定数
PHASE_DESIGN    = "design"
PHASE_IMPLEMENT = "implement"
PHASE_REVIEW    = "review"
PHASE_REFINE    = "refine"
PHASE_DONE      = "done"

PHASE_LABELS = {
    PHASE_DESIGN:    "🏗️ 設計フェーズ",
    PHASE_IMPLEMENT: "💻 実装フェーズ",
    PHASE_REVIEW:    "🔍 レビューフェーズ",
    PHASE_REFINE:    "🔧 修正フェーズ",
    PHASE_DONE:      "✅ 完成",
}


@dataclass
class PairResponse:
    phase:       str
    message:     str          # AIからのメッセージ
    code:        str = ""     # 生成されたコード（あれば）
    questions:   list = field(default_factory=list)  # ユーザーへの確認事項
    actions:     list = field(default_factory=list)  # 推奨アクション ["承認", "修正", "スキップ"]
    is_done:     bool = False


class PairSession:
    """
    1つの実装タスクに対する対話セッション。
    Streamlitのsession_stateに保存して使う。
    """

    def __init__(self, goal: str, anchor: str = "", save_path: str = "./",
                 model: str = "qwen2.5-coder:32b"):
        self.goal       = goal
        self.anchor     = anchor
        self.save_path  = save_path
        self.model      = model
        self.phase      = PHASE_DESIGN
        self.history    = []   # (role, content) のリスト
        self.design_doc = ""   # 承認された設計書
        self.code       = ""   # 現在のコード
        self.review_fb  = ""   # レビューフィードバック
        self.created_at = datetime.now().isoformat()

    @classmethod
    def start(cls, goal: str, anchor: str = "", save_path: str = "./",
              model: str = "qwen2.5-coder:32b") -> "PairSession":
        """新しいペアプログラミングセッションを開始する"""
        session = cls(goal, anchor, save_path, model)
        return session

    def _call(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Ollamaを呼ぶ内部ヘルパー"""
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            # 直近の会話履歴を追加（最大6ターン）
            for role, content in self.history[-6:]:
                messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": user})

            res = ollama.chat(model=self.model, messages=messages)
            reply = res["message"]["content"]
            self.history.append(("user",      user))
            self.history.append(("assistant", reply))
            return reply
        except Exception as e:
            return f"[ERROR: {e}]"

    # ────────────────────────────────────────────────────────
    # フェーズ別ハンドラ
    # ────────────────────────────────────────────────────────

    def _phase_design(self, user_input: str = "") -> PairResponse:
        """設計フェーズ: 実装方針を提案する"""
        system = (
            "あなたは優秀なペアプログラマーです。\n"
            "ユーザーの実装ゴールを聞いて、実装方針を提案してください。\n\n"
            "出力形式:\n"
            "## 実装方針\n"
            "- アプローチ: [一言]\n"
            "- クラス/関数構成: [箇条書き]\n"
            "- 注意点: [重要な考慮事項]\n"
            "- 想定行数: [概算]\n\n"
            "最後に「この方針でよいですか？修正点があれば教えてください。」と聞いてください。\n"
            f"{'【主軸】' + self.anchor if self.anchor else ''}"
        )

        if not user_input:
            user = f"以下を実装したい:\n{self.goal}"
        else:
            user = f"方針を修正してください:\n{user_input}\n\n元のゴール: {self.goal}"

        reply = self._call(system, user)
        return PairResponse(
            phase=PHASE_DESIGN,
            message=reply,
            actions=["✅ この方針で実装開始", "✏️ 方針を修正したい", "⏭️ 直接実装して"],
        )

    def _phase_implement(self, design_approved: str = "") -> PairResponse:
        """実装フェーズ: 承認された設計でコードを生成"""
        if design_approved:
            self.design_doc = design_approved

        system = (
            "あなたは優秀なコーダーです。\n"
            "以下の設計に従って、完全に動作するコードを生成してください。\n"
            "コードのみを出力し、余計な説明は不要です。\n"
            f"{'【主軸】' + self.anchor if self.anchor else ''}"
        )
        user = (
            f"【設計方針】\n{self.design_doc or '（設計なし - 直接実装）'}\n\n"
            f"【実装ゴール】\n{self.goal}"
        )

        reply   = self._call(system, user)
        # コード抽出
        m = re.search(r"```(?:\w+)?\n(.*?)```", reply, re.DOTALL)
        self.code = m.group(1).strip() if m else reply.strip()

        return PairResponse(
            phase=PHASE_IMPLEMENT,
            message="実装完了。コードをレビューします。",
            code=self.code,
            actions=["🔍 AIレビューを実行", "✅ このまま保存", "✏️ 修正指示を出す"],
        )

    def _phase_review(self) -> PairResponse:
        """レビューフェーズ: 自分のコードを批評する"""
        system = (
            "あなたは厳格なコードレビュアーです。\n"
            "以下のコードをレビューして、問題点を指摘してください。\n\n"
            "チェック項目:\n"
            "- バグ・クラッシュの可能性\n"
            "- エッジケースの考慮漏れ\n"
            "- パフォーマンス問題\n"
            "- 可読性・保守性\n"
            "- ゲーム固有の問題（該当する場合）\n\n"
            "問題があれば「要修正」、なければ「承認」と最後に書いてください。"
        )
        user = f"レビュー対象:\n```\n{self.code[:3000]}\n```"

        reply          = self._call(system, user)
        self.review_fb = reply
        needs_fix      = "要修正" in reply or "問題" in reply or "バグ" in reply

        if needs_fix:
            actions = ["🔧 指摘を自動修正", "✅ 問題なし・このまま保存", "✏️ 手動で修正指示"]
        else:
            actions = ["✅ 保存して完了", "✏️ 追加修正を指示"]

        return PairResponse(
            phase=PHASE_REVIEW,
            message=reply,
            code=self.code,
            actions=actions,
        )

    def _phase_refine(self, user_instruction: str = "") -> PairResponse:
        """修正フェーズ: レビュー指摘を反映して修正"""
        system = (
            "あなたは優秀なコーダーです。\n"
            "レビューの指摘を全て修正した完全なコードを出力してください。\n"
            "修正点のみ変えて、動作する完全なコードを返してください。"
        )
        fix_instruction = user_instruction or self.review_fb
        user = (
            f"【修正前コード】\n```\n{self.code[:2000]}\n```\n\n"
            f"【修正指示/レビュー】\n{fix_instruction[:1000]}"
        )

        reply   = self._call(system, user)
        m = re.search(r"```(?:\w+)?\n(.*?)```", reply, re.DOTALL)
        self.code = m.group(1).strip() if m else self.code

        return PairResponse(
            phase=PHASE_REFINE,
            message="修正完了。",
            code=self.code,
            actions=["✅ 保存して完了", "🔍 もう一度レビュー", "✏️ 追加修正を指示"],
        )

    # ────────────────────────────────────────────────────────
    # メインエントリポイント
    # ────────────────────────────────────────────────────────

    def respond(self, user_input: str = "", action: str = "") -> PairResponse:
        """
        ユーザーの入力またはアクションに応じてフェーズを進める。

        action: "approve" / "modify" / "skip" / "review" / "save" / "refine"
        """
        if self.phase == PHASE_DESIGN:
            if action == "approve" or "実装開始" in user_input:
                self.design_doc = user_input or "（承認済み）"
                self.phase = PHASE_IMPLEMENT
                return self._phase_implement()
            elif action == "skip" or "直接実装" in user_input:
                self.phase = PHASE_IMPLEMENT
                return self._phase_implement()
            else:
                return self._phase_design(user_input)

        elif self.phase == PHASE_IMPLEMENT:
            if action == "review" or "レビュー" in user_input:
                self.phase = PHASE_REVIEW
                return self._phase_review()
            elif action == "save" or "保存" in user_input:
                self.phase = PHASE_DONE
                return PairResponse(phase=PHASE_DONE, message="✅ 完成！コードを保存します。",
                                    code=self.code, is_done=True)
            else:
                # 修正指示
                return self._phase_implement(user_input)

        elif self.phase == PHASE_REVIEW:
            if action == "refine" or "修正" in user_input:
                self.phase = PHASE_REFINE
                return self._phase_refine(user_input)
            elif action == "save" or "保存" in user_input or "問題なし" in user_input:
                self.phase = PHASE_DONE
                return PairResponse(phase=PHASE_DONE, message="✅ 完成！",
                                    code=self.code, is_done=True)
            else:
                return self._phase_review()

        elif self.phase == PHASE_REFINE:
            if action == "save" or "保存" in user_input:
                self.phase = PHASE_DONE
                return PairResponse(phase=PHASE_DONE, message="✅ 修正完了・保存します。",
                                    code=self.code, is_done=True)
            elif action == "review" or "レビュー" in user_input:
                self.phase = PHASE_REVIEW
                return self._phase_review()
            else:
                return self._phase_refine(user_input)

        else:  # PHASE_DONE
            return PairResponse(phase=PHASE_DONE, message="このセッションは完了しています。",
                                code=self.code, is_done=True)

    def get_state(self) -> dict:
        return {
            "phase":     self.phase,
            "phase_label": PHASE_LABELS.get(self.phase, self.phase),
            "goal":      self.goal,
            "has_design": bool(self.design_doc),
            "has_code":   bool(self.code),
            "code_lines": len(self.code.splitlines()) if self.code else 0,
            "turns":      len(self.history) // 2,
        }
