from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def error(message: str) -> None:
    ERRORS.append(message)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        error(f"{path.relative_to(ROOT)} 缺少 Front Matter")
        return {}

    try:
        end = lines.index("---", 1)
    except ValueError:
        error(f"{path.relative_to(ROOT)} 的 Front Matter 未闭合")
        return {}

    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            error(f"{path.relative_to(ROOT)} 的 Front Matter 无法解析：{line}")
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def require(meta: dict[str, str], path: Path, *keys: str) -> None:
    for key in keys:
        if not meta.get(key):
            error(f"{path.relative_to(ROOT)} 缺少 {key}")


def validate_status(path: Path, allowed: set[str]) -> dict[str, str]:
    meta = parse_frontmatter(path)
    if meta.get("status") not in allowed:
        error(f"{path.relative_to(ROOT)} 的 status 不合法：{meta.get('status', '')}")
    return meta


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def validate() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "outlines/overall.md",
        "style/guide.md",
        "workflow/state.yaml",
        "workflow/prose-review/README.md",
        "workflow/prose-review/review-guide.md",
        "workflow/prose-review/experiments/README.md",
        "workflow/prose-review/experiments/record-template.md",
    ]
    for name in required:
        if not (ROOT / name).is_file():
            error(f"缺少必要文件：{name}")

    for path in sorted((ROOT / "manuscript").glob("*.md")):
        if path.name == "README.md":
            continue
        if not path.stem.isdigit():
            error(f"正文文件名必须只含数字：{path.relative_to(ROOT)}")
        meta = validate_status(path, {"draft", "awaiting_review", "accepted", "published"})
        require(meta, path, "volume", "chapter", "status")
        if meta.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
            error(f"{path.relative_to(ROOT)} 的 date 格式应为 YYYY-MM-DD")
        if meta.get("status") == "published" and not meta.get("date"):
            error(f"{path.relative_to(ROOT)} 发布前必须填写 date")

    overall = ROOT / "outlines" / "overall.md"
    if overall.is_file():
        meta = validate_status(overall, {"draft", "awaiting_approval", "approved"})
        require(meta, overall, "structure", "status")

    for path in sorted((ROOT / "outlines" / "chapters").glob("*.md")):
        meta = validate_status(path, {"draft", "awaiting_approval", "approved"})
        require(meta, path, "volume", "chapter", "pov", "status")

    for path in sorted((ROOT / "outlines" / "volumes").glob("*.md")):
        meta = validate_status(path, {"draft", "awaiting_approval", "approved"})
        require(meta, path, "volume", "status")

    style = ROOT / "style" / "guide.md"
    if style.is_file():
        meta = validate_status(style, {"draft", "approved"})
        require(meta, style, "status")

    publication = ROOT / "workflow" / "publication.yaml"
    if publication.is_file():
        text = publication.read_text(encoding="utf-8")
        enabled = re.search(r"(?m)^enabled:\s*true\s*$", text) is not None
        if enabled:
            for key in ("target_repository", "novel_slug", "volumes"):
                if re.search(rf"(?m)^{key}:\s*\S+", text) is None and key != "volumes":
                    error(f"启用发布时 workflow/publication.yaml 缺少 {key}")

    for path in tracked_files():
        relative = path.relative_to(ROOT)
        if relative.parts[0] == "workspace" and relative.name != "README.md":
            error(f"workspace 临时文件不应进入 Git：{relative}")
        if path.suffix.lower() not in {".md", ".yaml", ".yml", ".py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^(<<<<<<<|>>>>>>>)", text):
            error(f"发现 Git 冲突标记：{relative}")


validate()
if ERRORS:
    for item in ERRORS:
        print(f"ERROR: {item}", file=sys.stderr)
    raise SystemExit(1)

print("Repository validation passed.")
