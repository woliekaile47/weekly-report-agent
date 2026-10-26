from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    root: Path = ROOT
    data_dir: Path | None = None

    def __post_init__(self):
        load_dotenv(self.root / ".env", override=False)
        self.data_dir = Path(self.data_dir or os.getenv("DATA_DIR", "runtime"))
        if not self.data_dir.is_absolute():
            self.data_dir = self.root / self.data_dir
        self.data_dir = self.data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def mode(self):
        return "live"

    def employee(self) -> dict:
        config = yaml.safe_load((self.root / "config/employee.yaml").read_text(encoding="utf-8"))
        directory = (self.root / config["skill"]).resolve()
        if not directory.is_relative_to(self.root.resolve()):
            raise ValueError("技能目录必须位于项目中")
        skill = (directory / "SKILL.md").read_text(encoding="utf-8")
        parts = skill.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError("SKILL.md 缺少 YAML 元信息")
        meta = yaml.safe_load(parts[1])
        if meta.get("name") != directory.name or not meta.get("description"):
            raise ValueError("技能名称必须匹配目录且包含 description")
        references = "\n".join(p.read_text(encoding="utf-8") for p in sorted(directory.rglob("*.md")))
        config["instructions"] = references
        config["version"] = hashlib.sha256(
            (yaml.safe_dump(config, allow_unicode=True) + references).encode()
        ).hexdigest()[:16]
        for key, value in config["limits"].items():
            if not isinstance(value, (int, float)) or value < (
                0 if key in {"tool_retries", "model_retries", "qc_repairs"} else 1
            ):
                raise ValueError(f"无效限制：{key}")
        return config

    @property
    def base_url(self):
        return os.getenv("LLM_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")

    @property
    def model(self):
        return os.getenv("LLM_MODEL", "agnes-3.0-flash")

    @property
    def api_key(self):
        return os.getenv("LLM_API_KEY", "")
