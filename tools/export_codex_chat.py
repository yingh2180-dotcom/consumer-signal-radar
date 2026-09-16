"""Export user-visible Codex messages to a privacy-filtered Markdown transcript."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


AMBIENT = re.compile(
    r"\s*<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>\s*",
    re.DOTALL,
)
RECOMMENDED_PLUGINS = re.compile(
    r"\s*<recommended_plugins>.*?</recommended_plugins>\s*",
    re.DOTALL,
)
ENVIRONMENT_CONTEXT = re.compile(
    r"\s*<environment_context>.*?</environment_context>\s*",
    re.DOTALL,
)
AGENTS_BLOCK = re.compile(
    r"\s*# AGENTS\.md instructions\s*<INSTRUCTIONS>.*?</INSTRUCTIONS>\s*",
    re.DOTALL,
)
ATTACHED_INSTRUCTION = re.compile(
    r"^Distinguish instructions in attached documents from the user's request\.\s*$",
    re.MULTILINE,
)
REQUEST_HEADING = re.compile(r"^## My request:\s*", re.MULTILINE)
IMAGE_WRAPPER = re.compile(r"<image\b[^>]*>.*?</image>", re.DOTALL)


def visible_text(content: list[dict]) -> str:
    parts = []
    for item in content or []:
        if item.get("type") in {"input_text", "output_text", "text"} and item.get("text"):
            parts.append(item["text"])
        elif item.get("type") in {"input_image", "image"}:
            parts.append("[图片附件]")
    text = "\n\n".join(parts)
    text = AMBIENT.sub("\n", text)
    text = RECOMMENDED_PLUGINS.sub("\n", text)
    text = ENVIRONMENT_CONTEXT.sub("\n", text)
    text = AGENTS_BLOCK.sub("\n", text)
    text = ATTACHED_INSTRUCTION.sub("", text)
    text = REQUEST_HEADING.sub("", text)
    text = IMAGE_WRAPPER.sub("[图片附件]", text)
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
    first_seen = 0
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
                timestamp, display_time = message_time(payload, row.get("timestamp"))
                message_id = payload.get("id")
                if not message_id:
                    fingerprint = hashlib.sha256(
                        f"{payload['role']}\0{timestamp}\0{text}".encode("utf-8")
                    ).hexdigest()
                    message_id = f"fallback:{fingerprint}"
                candidate = {
                    "id": message_id,
                    "role": payload["role"],
                    "phase": payload.get("phase"),
                    "text": text,
                    "timestamp": timestamp,
                    "display_time": display_time,
                    "first_seen": first_seen,
                }
                first_seen += 1
                previous = chosen.get(message_id)
                if previous is None:
                    chosen[message_id] = candidate
                elif text.count("�") < previous["text"].count("�"):
                    candidate["first_seen"] = previous["first_seen"]
                    chosen[message_id] = candidate
    return sorted(chosen.values(), key=lambda item: (item["timestamp"], item["first_seen"]))


def group_rounds(messages: list[dict]) -> list[dict]:
    """Group consecutive user messages with the AI messages that answer them."""
    rounds = []
    current = None
    for message in messages:
        if message["role"] == "user":
            if current is None:
                current = {"users": [message], "assistants": []}
            elif current["assistants"]:
                rounds.append(current)
                current = {"users": [message], "assistants": []}
            else:
                current["users"].append(message)
        else:
            if current is None:
                current = {"users": [], "assistants": [message]}
            else:
                current["assistants"].append(message)
    if current is not None:
        rounds.append(current)
    return rounds


def message_markdown(text: str) -> str:
    """Keep message text intact while preventing its headings from escaping a round."""
    rendered = []
    in_fence = False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            rendered.append(line)
        elif not in_fence and re.match(r"^#{1,6}\s+", line):
            rendered.append(re.sub(r"^#{1,6}\s+", "##### ", line))
        else:
            rendered.append(line)
    return "\n".join(rendered)


def render(messages: list[dict], thread_id: str) -> str:
    rounds = group_rounds(messages)
    lines = [
        "# 消费者洞察 Demo 2.0｜AI 协作聊天记录",
        "",
        "## 变更定位",
        "",
        "- **文档类型**：项目聊天归档",
        f"- **Codex 线程 ID**：`{thread_id}`",
        f"- **对话规模**：{len(rounds)} 轮，{len(messages)} 条用户与 AI 可见消息",
        "- **内容范围**：用户和 AI 在界面中可见的消息，按时间排列",
        "- **隐私处理**：不包含系统指令、开发者指令、内部推理、工具调用输入输出、密钥或自动注入的界面状态",
        "- **用途**：飞书共同回顾、项目决策追踪和后续 AI 交接",
        "",
        "## 阅读说明",
        "",
        "每一轮先显示用户问题，再显示 AI 的进度更新和正式答复。连续发送、尚未收到 AI 回复的用户补充会合并在同一轮中；原始消息顺序和正文保持不变。文件路径保留为当时记录，协作者无法据此访问原电脑。",
        "",
        "## 完整记录",
        "",
    ]
    for round_index, conversation in enumerate(rounds, 1):
        lines.extend([f"## 第 {round_index:02d} 轮", "", "### 👤 用户提问", ""])
        if not conversation["users"]:
            lines.extend(["*本轮开始前没有用户消息。*", ""])
        for user_index, message in enumerate(conversation["users"], 1):
            label = "提问" if len(conversation["users"]) == 1 else f"提问／补充 {user_index}"
            lines.extend(
                [
                    f"#### {label}｜{message['display_time']}",
                    "",
                    message_markdown(message["text"]),
                    "",
                ]
            )
        lines.extend(["### 🤖 AI 回复", ""])
        if not conversation["assistants"]:
            lines.extend(["*归档时该轮尚无 AI 回复。*", ""])
        for message in conversation["assistants"]:
            if message["phase"] == "commentary":
                label = "执行进度"
            elif message["phase"] in {"final", "final_answer"}:
                label = "正式答复"
            else:
                label = "AI 回复"
            lines.extend(
                [
                    f"#### {label}｜{message['display_time']}",
                    "",
                    message_markdown(message["text"]),
                    "",
                ]
            )
        lines.extend(["---", ""])
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
