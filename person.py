"""Load the shared config.yaml merged with people/<name>/settings.yaml."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def load(name):
    folder = ROOT / "people" / name
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg.update(yaml.safe_load((folder / "settings.yaml").read_text(encoding="utf-8")))
    return cfg, folder


def words_pattern(words):
    """['intern\\b', 'junior'] -> regex matching any of them at the start of a word (case-insensitive)."""
    return re.compile(r"\b(?:" + "|".join(words) + ")", re.I) if words else re.compile(r"(?!)")
