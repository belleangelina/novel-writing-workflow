from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} 缺少有效 Front Matter")

    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"{path} 的 Front Matter 无法解析：{line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values, text[match.end():]


def parse_config(path: Path) -> dict[str, object]:
    values: dict[str, object] = {"volumes": {}}
    in_volumes = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line == "volumes:":
            in_volumes = True
            continue
        if in_volumes and line.startswith("  "):
            key, value = line.strip().split(":", 1)
            if value.strip():
                volumes = values["volumes"]
                assert isinstance(volumes, dict)
                volumes[int(key)] = value.strip()
            continue
        in_volumes = False
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def chinese_number(number: int) -> str:
    if number <= 0 or number >= 10000:
        return str(number)
    digits = "零一二三四五六七八九"
    units = ["", "十", "百", "千"]
    result: list[str] = []
    zero_pending = False
    text = str(number)
    for index, char in enumerate(text):
        digit = int(char)
        unit = units[len(text) - index - 1]
        if digit == 0:
            zero_pending = bool(result)
            continue
        if zero_pending:
            result.append("零")
            zero_pending = False
        result.append(digits[digit] + unit)
    rendered = "".join(result)
    return rendered[1:] if rendered.startswith("一十") else rendered


def render_chapter(meta: dict[str, str], body: str) -> str:
    chapter = int(meta["chapter"])
    published = meta.get("date")
    if not published:
        raise ValueError(f"第 {chapter} 章缺少 date")
    lines = [
        "---",
        f"title: 第{chinese_number(chapter)}章",
        "status: published",
        f"chapter: {chapter}",
        f"date: {published}",
    ]
    if "summary" in meta:
        lines.append(f"summary: {meta['summary']}")
    lines.extend(["---", "", body.lstrip("\r\n").rstrip() + "\n"])
    return "\n".join(lines)


def print_config(config_path: Path) -> None:
    config = parse_config(config_path)
    enabled = str(config.get("enabled", "false")).lower() == "true"
    print(f"enabled={'true' if enabled else 'false'}")
    print(f"target_repository={config.get('target_repository', '')}")


def sync(source_root: Path, target_root: Path, config_path: Path) -> None:
    config = parse_config(config_path)
    if str(config.get("enabled", "false")).lower() != "true":
        return

    novel_slug = str(config.get("novel_slug", ""))
    volumes = config.get("volumes")
    if not novel_slug or not isinstance(volumes, dict):
        raise ValueError("发布配置缺少 novel_slug 或 volumes")

    novel_root = target_root / "novels" / novel_slug
    if not (novel_root / "index.md").is_file():
        raise ValueError(f"目标作品目录不存在：{novel_root}")

    published_count = 0
    for source in sorted((source_root / "manuscript").glob("*.md")):
        if source.name == "README.md":
            continue
        meta, body = parse_frontmatter(source)
        if meta.get("status") != "published":
            continue

        volume = int(meta["volume"])
        chapter = int(meta["chapter"])
        volume_slug = volumes.get(volume)
        if not volume_slug:
            raise ValueError(f"第 {chapter} 章所属卷 {volume} 没有发布目录映射")

        volume_root = novel_root / str(volume_slug)
        if not (volume_root / "index.md").is_file():
            raise ValueError(f"目标卷目录不存在：{volume_root}")

        target = volume_root / f"chapter-{chapter}.md"
        rendered = render_chapter(meta, body)
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            target.write_text(rendered, encoding="utf-8", newline="\n")
        published_count += 1

    print(f"Reconciled {published_count} published chapter(s).")


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest="command", required=True)

config_parser = subparsers.add_parser("config")
config_parser.add_argument("--config", type=Path, required=True)

sync_parser = subparsers.add_parser("sync")
sync_parser.add_argument("--source-root", type=Path, required=True)
sync_parser.add_argument("--target-root", type=Path, required=True)
sync_parser.add_argument("--config", type=Path, required=True)

args = parser.parse_args()
if args.command == "config":
    print_config(args.config)
else:
    sync(args.source_root, args.target_root, args.config)
