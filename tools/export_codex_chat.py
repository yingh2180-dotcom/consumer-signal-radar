"""Export user-visible Codex messages to a privacy-filtered Markdown transcript."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


AMBIENT = re.compile(
    r"\s*<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>\s*",
    re.DOTALL,
)
AGENTS_BLOCK = re.compile(
    r"\s*# AGENTS\.md instructions\s*<INSTRUCTIONS>.*?</INSTRUCTIONS>.*?</environment_context>\s*",
    re.DOTALL,
)


def visible_text(content: list[dict]) -> str:
    parts = []
    for item in content or []:
        if item.get("type") in {"input_text", "output_text", "text"} and item.get("text"):
            parts.append(item["text"])
        elif item.get("type") in {"input_image", "image"}:
            parts.append("[图片附件]")
    text = "\n\n".join(parts)
    text = AMBIENT.sub("\n", text)
    text = AGENTS_BLOCK.sub("\n", text)
    text = text.replace("&#x20;", " ")
    return text.strip()


def message_time(payload: dict, fallback: str | None) -> tuple[float, str]:
    meta = payload.get("internal_chat_message_metadata_passthrough") or {}
    value = meta.get("create_time")
    if isinstance(value, (int, float)):
        moment = datetime.fromtimestamp(value, ZoneInfo("Asia/Shanghai"))
        return float(value), moment.strftime("%Y-%m-%d %H:%M:%S")
    if fallback:
        try:
            moment = datetime.fromisoformat(fallback.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai"))
            return moment.timestamp(), moment.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return 0.0, "时间未记录"


def collect(paths: list[Path]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                if row.get("type") != "response_item":
                    continue
                payload = row.get("payload") or {}
                if payload.get("type") != "message" or payload.get("role") not in {"user", "assistant"}:
                    continue
                text = visible_text(payload.get("content") or [])
                if not text:
                    continue
                message_id = payload.get("id") or f"{path.name}:{row.get('timestamp')}:{len(chosen)}"
                timestamp, display_time = message_time(payload, row.get("timestamp"))
                candidate = {
                    "id": message_id,
                    "role": payload["role"],
                    "phase": payload.get("phase"),
                    "text": text,
                    "timestamp": timestamp,
                    "display_time": display_time,
                }
                previous = chosen.get(message_id)
                if previous is None or text.count("�") < previous["text"].count("�"):
                    chosen[message_id] = candidate
    messages = sorted(chosen.values(), key=lambda item: (item["timestamp"], item["id"]))
    deduped = []
    seen = set()
    for message in messages:
        key = (message["role"], re.sub(r"\s+", " ", message["text"]).strip())
        if key not in seen:
            seen.add(key)
            deduped.append(message)
    return deduped


def render(messages: list[dict], thread_id: str) -> str:
    lines = [
        "# 消费者洞察 Demo 2.0｜AI 协作聊天记录",
        "",
        "## 变更定位",
        "",
        "- **文档类型**：项目聊天归档",
        f"- **Codex 线程 ID**：`{thread_id}`",
        "- **内容范围**：用户和 AI 在界面中可见的消息，按时间排列",
        "- **隐私处理**：不包含系统指令、开发者指令、内部推理、工具调用输入输出、密钥或自动注入的界面状态",
        "- **用途**：飞书共同回顾、项目决策追踪和后续 AI 交接",
        "",
        "## 阅读说明",
        "",
        "“AI · 进度更新”表示执行过程中的可见说明；“AI · 正式答复”表示该轮最终交付。文件路径保留为当时记录，协作者无法据此访问原电脑。",
        "",
        "## 完整记录",
        "",
    ]
    for index, message in enumerate(messages, 1):
        if message["role"] == "user":
            label = "用户"
        elif message["phase"] == "commentary":
            label = "AI · 进度更新"
        else:
            label = "AI · 正式答复"
        lines.extend(
            [
                f"### {index}. {label}｜{message['display_time']}",
                "",
                message["text"],
                "",
            ]
        )
    lines.extend(
        [
            "## 归档边界",
            "",
            "本文件用于复现用户可见的协作过程。正式产品状态、验收结果和后续步骤以《Demo 2.0 当前完成情况与后续执行计划》及 GitHub 当前正式分支为准。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--sessions-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.sessions_root.rglob(f"*{args.thread_id}*.jsonl"))
    if not paths:
        raise SystemExit("No rollout files found for the requested thread")
    messages = collect(paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(messages, args.thread_id), encoding="utf-8")
    print(f"Exported {len(messages)} messages to {args.output}")


if __name__ == "__main__":
    main()
