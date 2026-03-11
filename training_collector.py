"""
Blackwell Dev-OS — training_collector.py v1.0  (Phase 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 5 パート1: 学習データ自動収集

【何をするか】
  Blackwellがコードを生成するたびに「教師データ」として保存する。
  人間のレビューなしに、成功したコードだけが学習データになる。

  保存形式: JSONL（1行1サンプル）
  {
    "prompt":    "タスクの説明（入力）",
    "response":  "生成したコード（出力）",
    "score":     82,
    "language":  "gdscript",
    "tags":      ["jump", "movement"],
    "timestamp": "2026-03-11T..."
  }

【品質フィルタリング】
  スコア70以上のみ学習データに採用。
  失敗したコード・低品質なコードは除外する。
  これにより「良いコードだけ」から学習できる。

【ファインチューニング形式への変換】
  Ollama Modelfile用のalpaca形式に自動変換:
  {
    "instruction": "...",
    "input": "",
    "output": "..."
  }

【保存先】
  {project_path}/blackwell_brain/training_data.jsonl   ← 生データ
  {project_path}/blackwell_brain/finetune_alpaca.jsonl ← 変換済み
  {project_path}/blackwell_brain/training_stats.json   ← 統計

【公開API】
  collect(path, task, code, score, language, tags, thinking_log)
  get_stats(path)              → dict
  export_for_finetuning(path)  → str (export先パス)
  should_finetune(path)        → bool (100件超えたら True)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
from datetime import datetime


BRAIN_DIR       = "blackwell_brain"
TRAINING_FILE   = "training_data.jsonl"
ALPACA_FILE     = "finetune_alpaca.jsonl"
STATS_FILE      = "training_stats.json"

MIN_SCORE       = 70    # このスコア以上のみ学習データに採用
MIN_CODE_LINES  = 5     # 最低行数（短すぎるコードは除外）
FINETUNE_THRESHOLD = 100  # この件数を超えたらファインチューニング推奨


# ============================================================
# データ収集
# ============================================================

def collect(project_path: str,
            task_desc: str,
            code: str,
            score: int,
            language: str = "",
            tags: list = None,
            thinking_log: dict = None,
            file_name: str = "") -> bool:
    """
    タスク完了後に自動呼び出し。
    スコア70以上のコードだけ学習データとして保存する。

    Returns: True=保存した / False=スキップ（品質不足）
    """
    # 品質フィルタ
    if score < MIN_SCORE:
        return False
    if len(code.splitlines()) < MIN_CODE_LINES:
        return False
    if not task_desc.strip() or not code.strip():
        return False

    # 言語の自動検出
    if not language:
        language = _detect_language(code, file_name)

    # プロンプトの構築（思考ログがある場合は思考過程も含める）
    prompt = _build_prompt(task_desc, language, thinking_log)

    sample = {
        "prompt":      prompt,
        "response":    code,
        "score":       score,
        "language":    language,
        "tags":        tags or [],
        "file":        file_name,
        "timestamp":   datetime.now().isoformat(),
        "has_thinking": thinking_log is not None,
    }

    # 保存
    brain = _brain_dir(project_path)
    path  = os.path.join(brain, TRAINING_FILE)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 統計更新
    _update_stats(project_path, language, score)

    print(f"[training] データ収集: score={score} lang={language} {file_name}")
    return True


def _build_prompt(task_desc: str, language: str,
                  thinking_log: dict = None) -> str:
    """
    学習データのプロンプト部分を構築する。
    思考ログがある場合はCoTスタイルのプロンプトにする。
    これにより「なぜそう実装したか」まで学習できる。
    """
    base = f"以下のタスクを{language}で実装してください。\n\nタスク: {task_desc}"

    if thinking_log and thinking_log.get("final_reasoning"):
        # 思考過程付きプロンプト（より価値が高い学習データ）
        reasoning = thinking_log["final_reasoning"]
        complexity = thinking_log.get("complexity", "?")
        base += (
            f"\n\n【実装の方針（複雑さ{complexity}/5）】\n{reasoning}"
        )

    return base


def _detect_language(code: str, file_name: str = "") -> str:
    """コードの言語を判定する"""
    ext = os.path.splitext(file_name)[1].lower() if file_name else ""
    if ext == ".py":
        return "python"
    if ext == ".gd":
        return "gdscript"
    if ext == ".cs":
        return "csharp"

    # 内容から判定
    if re.search(r"extends\s+\w+|func\s+_ready|@onready", code):
        return "gdscript"
    if re.search(r"using\s+UnityEngine|public\s+class.*:.*MonoBehaviour", code):
        return "csharp"
    if re.search(r"^import\s+\w+|^def\s+\w+|^class\s+\w+:", code, re.MULTILINE):
        return "python"
    return "unknown"


# ============================================================
# エクスポート（ファインチューニング用）
# ============================================================

def export_for_finetuning(project_path: str,
                          min_score: int = MIN_SCORE) -> str:
    """
    training_data.jsonlをOllama/Llamaファインチューニング用の
    alpaca形式に変換して保存する。

    alpaca形式:
    {
      "instruction": "タスクの説明",
      "input": "",
      "output": "コード"
    }

    Returns: 出力ファイルのパス
    """
    brain    = _brain_dir(project_path)
    src_path = os.path.join(brain, TRAINING_FILE)
    dst_path = os.path.join(brain, ALPACA_FILE)

    if not os.path.exists(src_path):
        print("[training] 学習データファイルが存在しません")
        return ""

    samples = []
    with open(src_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                sample = json.loads(line)
                if sample.get("score", 0) >= min_score:
                    samples.append(sample)
            except Exception:
                continue

    if not samples:
        print("[training] エクスポート対象サンプルなし")
        return ""

    # alpaca形式に変換
    alpaca_samples = []
    for s in samples:
        alpaca_samples.append({
            "instruction": s["prompt"],
            "input":       "",
            "output":      s["response"],
        })

    # 重複除去（同じプロンプトが複数ある場合は最高スコアを残す）
    seen = {}
    for orig, alpha in zip(samples, alpaca_samples):
        key = alpha["instruction"][:100]
        if key not in seen or orig["score"] > seen[key]["score"]:
            seen[key] = {"alpha": alpha, "score": orig["score"]}

    deduped = [v["alpha"] for v in seen.values()]

    # 保存
    with open(dst_path, "w", encoding="utf-8") as f:
        for sample in deduped:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"[training] エクスポート完了: {len(deduped)}件 → {dst_path}")
    return dst_path


# ============================================================
# Modelfile生成（Ollamaファインチューニング用）
# ============================================================

def generate_modelfile(project_path: str,
                       base_model: str = "qwen2.5-coder:7b",
                       custom_model_name: str = "blackwell-custom") -> str:
    """
    Ollamaで使えるModelfileを生成する。
    これをもとに `ollama create` でカスタムモデルを作れる。

    Returns: Modelfileのパス
    """
    brain     = _brain_dir(project_path)
    alpaca    = os.path.join(brain, ALPACA_FILE)
    modelfile_path = os.path.join(brain, "Modelfile")

    stats = get_stats(project_path)
    langs = stats.get("by_language", {})
    lang_info = " / ".join(f"{k}:{v}" for k, v in langs.items())

    # プロジェクト特化のシステムプロンプトを生成
    system_prompt = (
        "あなたはBlackwell Dev-OSに統合された専用コーディングAIです。\n"
        "このプロジェクトのコードベースを深く理解しており、\n"
        "一貫したスタイルと設計思想でコードを生成します。\n\n"
        f"対応言語: {lang_info}\n"
        f"学習データ: {stats.get('total', 0)}件のタスク\n"
        f"平均スコア: {stats.get('avg_score', 0)}/100\n\n"
        "コードを生成するときは:\n"
        "1. このプロジェクトのコーディングスタイルに従う\n"
        "2. エラーハンドリングを必ず実装する\n"
        "3. コメントは日本語で書く\n"
        "4. GDScriptではdeltaを必ず意識する\n"
    )

    modelfile_content = (
        f"FROM {base_model}\n\n"
        f"SYSTEM \"\"\"\n{system_prompt}\"\"\"\n\n"
        f"# 学習データ: {alpaca}\n"
        f"# カスタムモデル名: {custom_model_name}\n\n"
        f"# 使い方:\n"
        f"# 1. ollama create {custom_model_name} -f Modelfile\n"
        f"# 2. app.pyのMODELS[\"coder\"]を\"{custom_model_name}\"に変更\n\n"
        f"PARAMETER temperature 0.3\n"
        f"PARAMETER top_p 0.9\n"
        f"PARAMETER num_ctx 8192\n"
    )

    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    print(f"[training] Modelfile生成: {modelfile_path}")
    return modelfile_path


def generate_finetune_script(project_path: str,
                              base_model: str = "qwen2.5-coder:7b",
                              custom_model_name: str = "blackwell-custom") -> str:
    """
    ファインチューニング実行スクリプト（run_finetune.py）を生成する。
    unsloth を使った効率的なLoRAファインチューニング。

    Returns: スクリプトのパス
    """
    brain      = _brain_dir(project_path)
    alpaca     = os.path.join(brain, ALPACA_FILE)
    script_path = os.path.join(brain, "run_finetune.py")

    script = f'''"""
Blackwell Dev-OS — ファインチューニング実行スクリプト
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
必要なライブラリ:
  pip install unsloth torch transformers datasets

実行方法:
  python run_finetune.py

完了後:
  ./blackwell_model/ にモデルが保存されます
  ollama create {custom_model_name} -f Modelfile
  app.pyのMODELS["coder"]を"{custom_model_name}"に変更
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os

ALPACA_DATA = r"{alpaca}"
OUTPUT_DIR  = "./blackwell_model"
BASE_MODEL  = "{base_model}"
MAX_SEQ_LEN = 2048
EPOCHS      = 3
BATCH_SIZE  = 2

def load_dataset():
    samples = []
    with open(ALPACA_DATA, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    print(f"学習データ: {{len(samples)}}件")
    return samples

def format_prompt(sample):
    return (
        "### Instruction:\\n{{instruction}}\\n\\n"
        "### Response:\\n{{output}}"
    ).format(**sample)

def main():
    try:
        from unsloth import FastLanguageModel
        import torch
        from datasets import Dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
    except ImportError as e:
        print(f"必要なライブラリが不足: {{e}}")
        print("pip install unsloth torch transformers datasets trl")
        return

    print("モデルを読み込み中...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
    )

    # LoRAアダプターを追加
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing=True,
    )

    # データセット準備
    raw_samples = load_dataset()
    formatted   = [{{"text": format_prompt(s)}} for s in raw_samples]
    dataset     = Dataset.from_list(formatted)

    # トレーニング
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=4,
            num_train_epochs=EPOCHS,
            learning_rate=2e-4,
            output_dir=OUTPUT_DIR,
            logging_steps=10,
            save_strategy="epoch",
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            optim="adamw_8bit",
        ),
    )

    print("ファインチューニング開始...")
    trainer.train()

    # GGUF形式で保存（Ollama用）
    model.save_pretrained_gguf(
        OUTPUT_DIR,
        tokenizer,
        quantization_method="q4_k_m",
    )
    print(f"完了！モデルを保存: {{OUTPUT_DIR}}")
    print(f"次のステップ: ollama create {custom_model_name} -f Modelfile")

if __name__ == "__main__":
    main()
'''

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"[training] ファインチューニングスクリプト生成: {script_path}")
    return script_path


# ============================================================
# 統計
# ============================================================

def get_stats(project_path: str) -> dict:
    """学習データの統計情報を返す"""
    brain     = _brain_dir(project_path)
    src_path  = os.path.join(brain, TRAINING_FILE)
    stats_path = os.path.join(brain, STATS_FILE)

    if not os.path.exists(src_path):
        return {
            "total": 0, "avg_score": 0,
            "by_language": {}, "ready_for_finetune": False,
            "finetune_threshold": FINETUNE_THRESHOLD,
        }

    # ファイルから直接集計
    total = 0
    scores = []
    by_lang = {}
    by_tag  = {}

    with open(src_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                total += 1
                scores.append(s.get("score", 0))
                lang = s.get("language", "unknown")
                by_lang[lang] = by_lang.get(lang, 0) + 1
                for tag in s.get("tags", []):
                    by_tag[tag] = by_tag.get(tag, 0) + 1
            except Exception:
                continue

    avg = sum(scores) // len(scores) if scores else 0
    result = {
        "total":              total,
        "avg_score":          avg,
        "by_language":        by_lang,
        "top_tags":           sorted(by_tag.items(),
                                     key=lambda x: -x[1])[:5],
        "ready_for_finetune": total >= FINETUNE_THRESHOLD,
        "finetune_threshold": FINETUNE_THRESHOLD,
        "progress_pct":       min(100, int(total / FINETUNE_THRESHOLD * 100)),
    }

    # キャッシュ保存
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def should_finetune(project_path: str) -> bool:
    """ファインチューニングを推奨するかどうか"""
    stats = get_stats(project_path)
    return stats.get("ready_for_finetune", False)


def get_recent_samples(project_path: str, n: int = 10) -> list:
    """直近n件のサンプルをapp.py表示用に返す"""
    brain    = _brain_dir(project_path)
    src_path = os.path.join(brain, TRAINING_FILE)

    if not os.path.exists(src_path):
        return []

    samples = []
    with open(src_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except Exception:
                    pass

    result = []
    for s in reversed(samples[-n:]):
        result.append({
            "timestamp": s.get("timestamp", "")[:16].replace("T", " "),
            "file":      s.get("file", ""),
            "score":     s.get("score", 0),
            "language":  s.get("language", ""),
            "tags":      s.get("tags", []),
            "has_thinking": s.get("has_thinking", False),
            "prompt_preview": s.get("prompt", "")[:60],
        })
    return result


# ============================================================
# 内部ユーティリティ
# ============================================================

def _brain_dir(project_path: str) -> str:
    d = os.path.join(project_path, BRAIN_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _update_stats(project_path: str, language: str, score: int):
    """統計を軽量更新する"""
    brain      = _brain_dir(project_path)
    stats_path = os.path.join(brain, STATS_FILE)

    stats = {}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, encoding="utf-8") as f:
                stats = json.load(f)
        except Exception:
            stats = {}

    stats["total"]     = stats.get("total", 0) + 1
    stats["last_added"] = datetime.now().isoformat()

    by_lang = stats.get("by_language", {})
    by_lang[language] = by_lang.get(language, 0) + 1
    stats["by_language"] = by_lang

    # 移動平均でavg_scoreを更新
    n   = stats["total"]
    old = stats.get("avg_score", 0)
    stats["avg_score"] = int((old * (n - 1) + score) / n)
    stats["ready_for_finetune"] = stats["total"] >= FINETUNE_THRESHOLD
    stats["progress_pct"] = min(100, int(
        stats["total"] / FINETUNE_THRESHOLD * 100))

    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
