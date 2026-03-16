#!/usr/bin/env python3
"""
宅建テンプレートシステム - ビルドスクリプト
=============================================
テンプレートHTMLとJSONデータからアプリHTMLを生成する。

使い方:
  python build.py                    # 全てのJSONからHTMLを生成
  python build.py chintaishaku       # 指定アプリのみ生成
  python build.py --check            # JSONバリデーションのみ
  python build.py --list             # 利用可能なデータ一覧
"""

import json
import os
import sys
import glob
import re
from pathlib import Path
from typing import Optional

# ===== 設定 =====
BASE_DIR = Path(__file__).parent.parent
TEMPLATE_PATH = BASE_DIR / "template" / "template.html"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# テンプレート内のプレースホルダ一覧
PLACEHOLDERS = {
    "{{APP_ID}}":            "app_id",
    "{{APP_TITLE}}":         "app_title",
    "{{HEADER_TITLE}}":      "header_title",
    "{{HEADER_DESC}}":       "header_desc",
    "{{QUIZ_TITLE}}":        "quiz_title",
    "{{QUIZZES_L1}}":        "quizzes_l1",
    "{{QUIZZES_L2}}":        "quizzes_l2",
    "{{ABOUT_CONTENT}}":     "about_content",
    "{{PRINCIPLE_CONTENT}}":  "principle_content",
}

# JSONに指定がない場合のデフォルト値
PLACEHOLDER_DEFAULTS = {
    "{{MENU_URL}}": "index.html",
}

# JSON必須フィールド
REQUIRED_FIELDS = [
    "app_id", "app_title", "header_title", "header_desc", "quiz_title",
    "quizzes_l1", "quizzes_l2", "about_content", "principle_content"
]

# クイズの必須フィールド
QUIZ_REQUIRED_FIELDS = ["q", "a", "ex", "cat"]


class BuildError(Exception):
    """ビルドエラー"""
    pass


class TermColor:
    """ターミナルカラー"""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

    @staticmethod
    def ok(msg): return f"{TermColor.GREEN}✅ {msg}{TermColor.END}"
    @staticmethod
    def warn(msg): return f"{TermColor.YELLOW}⚠️  {msg}{TermColor.END}"
    @staticmethod
    def err(msg): return f"{TermColor.RED}❌ {msg}{TermColor.END}"
    @staticmethod
    def info(msg): return f"{TermColor.BLUE}ℹ️  {msg}{TermColor.END}"
    @staticmethod
    def bold(msg): return f"{TermColor.BOLD}{msg}{TermColor.END}"


def load_template() -> str:
    """テンプレートHTMLを読み込む"""
    if not TEMPLATE_PATH.exists():
        raise BuildError(f"テンプレートが見つかりません: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def load_json(json_path: Path) -> dict:
    """JSONデータを読み込み・バリデーション"""
    if not json_path.exists():
        raise BuildError(f"JSONファイルが見つかりません: {json_path}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise BuildError(f"JSON解析エラー ({json_path.name}): {e}")

    return data


def validate_json(data: dict, filename: str) -> list[str]:
    """JSONデータを検証し、問題のリストを返す"""
    issues = []

    # 必須フィールドチェック
    for field in REQUIRED_FIELDS:
        if field not in data:
            issues.append(f"必須フィールド '{field}' がありません")

    # app_id チェック
    if "app_id" in data:
        if not re.match(r'^[a-z_]+$', data["app_id"]):
            issues.append(f"app_id は半角小文字英字とアンダースコアのみ使用可能です: '{data['app_id']}'")

    # クイズ配列チェック
    for level_key in ["quizzes_l1", "quizzes_l2"]:
        if level_key in data:
            quizzes = data[level_key]
            if not isinstance(quizzes, list):
                issues.append(f"'{level_key}' は配列である必要があります")
                continue
            if len(quizzes) == 0:
                issues.append(f"'{level_key}' が空です（最低1問必要）")
            for i, quiz in enumerate(quizzes):
                for qf in QUIZ_REQUIRED_FIELDS:
                    if qf not in quiz:
                        issues.append(f"{level_key}[{i}] に '{qf}' がありません")
                if "a" in quiz and not isinstance(quiz["a"], bool):
                    issues.append(f"{level_key}[{i}] の 'a' はbool型（true/false）である必要があります")

    # HTML コンテンツチェック
    for content_key in ["about_content", "principle_content"]:
        if content_key in data:
            content = data[content_key]
            if not isinstance(content, str):
                issues.append(f"'{content_key}' は文字列である必要があります")
            elif len(content) < 50:
                issues.append(f"'{content_key}' が短すぎます（50文字未満）")

    return issues


def build_html(template: str, data: dict) -> str:
    """テンプレートにデータを埋め込んでHTMLを生成"""
    html = template

    for placeholder, json_key in PLACEHOLDERS.items():
        if json_key not in data:
            raise BuildError(f"JSONに '{json_key}' がありません（プレースホルダ: {placeholder}）")

        value = data[json_key]

        # 配列（クイズ）はJSON文字列に変換
        if isinstance(value, list):
            replacement = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            replacement = str(value)

        html = html.replace(placeholder, replacement)

    # デフォルト値つきのプレースホルダを処理（JSONに指定がなければデフォルト値を使用）
    for placeholder, default_value in PLACEHOLDER_DEFAULTS.items():
        json_key = placeholder.strip("{}").lower()
        value = data.get(json_key, default_value)
        html = html.replace(placeholder, str(value))

    # 残っているプレースホルダがないか確認
    remaining = re.findall(r'\{\{[A-Z_]+\}\}', html)
    if remaining:
        raise BuildError(f"未置換のプレースホルダが残っています: {remaining}")

    return html


def get_data_files() -> list[Path]:
    """data/ ディレクトリのJSONファイル一覧を取得"""
    if not DATA_DIR.exists():
        raise BuildError(f"データディレクトリが見つかりません: {DATA_DIR}")
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        raise BuildError(f"JSONファイルが見つかりません: {DATA_DIR}")
    return files


def build_single(json_path: Path, template: str, dry_run: bool = False) -> Optional[Path]:
    """単一のJSONからHTMLをビルド"""
    app_name = json_path.stem
    print(f"\n{TermColor.bold(f'--- {app_name} ---')}")

    # JSON読み込み
    data = load_json(json_path)

    # バリデーション
    issues = validate_json(data, json_path.name)
    if issues:
        for issue in issues:
            print(TermColor.warn(issue))
        if any("必須フィールド" in i for i in issues):
            print(TermColor.err(f"{app_name}: 必須フィールド不足のためスキップ"))
            return None
        print(TermColor.warn(f"{app_name}: 警告がありますが続行します"))
    else:
        print(TermColor.ok("バリデーション通過"))

    # 統計表示
    l1_count = len(data.get("quizzes_l1", []))
    l2_count = len(data.get("quizzes_l2", []))
    print(TermColor.info(f"Level1: {l1_count}問 / Level2: {l2_count}問 / 合計: {l1_count + l2_count}問"))

    if dry_run:
        print(TermColor.info("ドライランのためHTML生成をスキップ"))
        return None

    # HTML生成
    html = build_html(template, data)

    # 出力
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{app_name}.html"
    output_path.write_text(html, encoding="utf-8")

    file_size = output_path.stat().st_size / 1024
    print(TermColor.ok(f"生成完了: {output_path.name} ({file_size:.1f} KB)"))
    return output_path


def cmd_build(targets: list[str] = None):
    """ビルドコマンド"""
    print(TermColor.bold("🏗️  宅建テンプレートシステム - ビルド開始"))
    print(f"テンプレート: {TEMPLATE_PATH}")
    print(f"データ: {DATA_DIR}")
    print(f"出力先: {OUTPUT_DIR}")

    template = load_template()

    if targets:
        json_files = []
        for t in targets:
            p = DATA_DIR / f"{t}.json"
            if not p.exists():
                print(TermColor.err(f"ファイルが見つかりません: {p}"))
                sys.exit(1)
            json_files.append(p)
    else:
        json_files = get_data_files()

    print(f"\n対象: {len(json_files)} ファイル")

    results = {"success": [], "failed": [], "skipped": []}
    for jf in json_files:
        try:
            output = build_single(jf, template)
            if output:
                results["success"].append(jf.stem)
            else:
                results["skipped"].append(jf.stem)
        except BuildError as e:
            print(TermColor.err(str(e)))
            results["failed"].append(jf.stem)

    # サマリー
    print(f"\n{TermColor.bold('=== ビルド結果 ===')}")
    if results["success"]:
        print(TermColor.ok(f"成功: {', '.join(results['success'])}"))
    if results["skipped"]:
        print(TermColor.warn(f"スキップ: {', '.join(results['skipped'])}"))
    if results["failed"]:
        print(TermColor.err(f"失敗: {', '.join(results['failed'])}"))
        sys.exit(1)

    print(TermColor.ok("完了！"))


def cmd_check():
    """バリデーションのみ"""
    print(TermColor.bold("🔍 JSONバリデーション"))
    json_files = get_data_files()
    all_ok = True

    for jf in json_files:
        data = load_json(jf)
        issues = validate_json(data, jf.name)
        if issues:
            print(TermColor.err(f"{jf.name}:"))
            for issue in issues:
                print(f"   {issue}")
            all_ok = False
        else:
            l1 = len(data.get("quizzes_l1", []))
            l2 = len(data.get("quizzes_l2", []))
            print(TermColor.ok(f"{jf.name} (L1:{l1}問, L2:{l2}問)"))

    if all_ok:
        print(TermColor.ok("\n全てのJSONが正常です"))
    else:
        print(TermColor.err("\n問題があるJSONがあります"))
        sys.exit(1)


def cmd_list():
    """データ一覧"""
    print(TermColor.bold("📋 利用可能なデータ一覧"))
    try:
        json_files = get_data_files()
    except BuildError:
        print("データファイルがありません")
        return

    for jf in json_files:
        try:
            data = load_json(jf)
            title = data.get("app_title", "（タイトルなし）")
            l1 = len(data.get("quizzes_l1", []))
            l2 = len(data.get("quizzes_l2", []))
            print(f"  {jf.stem:20s} | {title} | L1:{l1}問 L2:{l2}問")
        except BuildError as e:
            print(f"  {jf.stem:20s} | エラー: {e}")


def main():
    args = sys.argv[1:]

    if not args:
        cmd_build()
    elif args[0] == "--check":
        cmd_check()
    elif args[0] == "--list":
        cmd_list()
    elif args[0] == "--help":
        print(__doc__)
    else:
        cmd_build(targets=args)


if __name__ == "__main__":
    main()
