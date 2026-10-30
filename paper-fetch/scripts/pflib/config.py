"""The one config file: every setting and secret of the skill, outside any repository.

~/.config/paper-fetch/config.json ($PAPER_FETCH_CONFIG points elsewhere, for tests), mode 600:
{"openalex_key", "institution": {"proxy", "discovery"}}. Every field is optional; a missing one turns its feature
off. No value read here is ever printed.

path, read, section and text are copied from paper-to-zotero/scripts/p2zlib/config.py (commit 90cecdf); each skill
reads its own file, so neither depends on the other being installed.
"""
import json
import os
from pathlib import Path

from .cli import CANNOT, Stop

ENV = "PAPER_FETCH_CONFIG"


def path():
    return Path(os.environ.get(ENV) or Path.home() / ".config" / "paper-fetch" / "config.json")


def read(strict=True):
    """The config as a dict ({} when there is none). Unreadable: Stop config_unreadable when strict, else {}."""
    p = path()
    try:
        config = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        if strict:
            raise Stop("config_unreadable", exit=CANNOT, hint="The config file is unreadable; fix it, then rerun.",
                       config=str(p), detail=str(e)) from None
        return {}
    if not isinstance(config, dict):
        if strict:
            raise Stop("config_unreadable", exit=CANNOT, hint="The config file must hold one JSON object; fix it, then rerun.",
                       config=str(p))
        return {}
    return config


def section(name, strict=False):
    value = read(strict).get(name)
    return value if isinstance(value, dict) else {}


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def institution():
    """{"proxy": the proxy's domain, lowercased, "discovery": the discovery search page}, None where unset."""
    inst = section("institution")
    proxy = text(inst.get("proxy"))
    return {"proxy": proxy.lower().lstrip(".") if proxy else None, "discovery": text(inst.get("discovery"))}


def openalex_key():
    return text(read(strict=False).get("openalex_key"))
