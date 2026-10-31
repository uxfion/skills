"""The skill's config file, outside any repository: the Zotero write key.

~/.config/paper-to-zotero/config.json ($PAPER_TO_ZOTERO_CONFIG points elsewhere, for tests), mode 600:
{"zotero": {"key", "serverID", "created"}, "automatic_tags"?: true | false}; ready.py --authorize writes the key,
the user sets automatic_tags (draft_item.py: the source's own keywords as automatic tags; off when absent). Other fields are kept as they are (the
openalex key and institution an older version kept here are paper-fetch's now, in its own config). No value read
here is ever printed.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from .cli import CANNOT, Stop

ENV = "PAPER_TO_ZOTERO_CONFIG"


def path():
    return Path(os.environ.get(ENV) or Path.home() / ".config" / "paper-to-zotero" / "config.json")


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


def automatic_tags():
    """Whether drafted items get the source's own keywords as automatic tags: the user's automatic_tags, off when absent."""
    return read(strict=False).get("automatic_tags") is True


def zotero_key(server_id):
    """The local API key ready.py --authorize stored, checked against the running instance's server id."""
    zot = section("zotero", strict=True)
    if not text(zot.get("key")):
        raise Stop("no_key", exit=CANNOT, hint="No local API key yet; run ready.py --authorize first.", config=str(path()))
    if zot.get("serverID") and zot["serverID"] != server_id:
        raise Stop("server_mismatch", exit=CANNOT,
                   hint="The stored key was issued by another Zotero instance; run ready.py --authorize again.",
                   config=str(path()))
    return zot["key"]


def save_key(key, server_id):
    """Write the "zotero" block, keeping every other field; mode 600, replaced at once. An unreadable config stops it:
    a file it cannot read is not overwritten."""
    p = path()
    config = read(strict=True)
    config["zotero"] = {"key": key, "serverID": server_id,
                        "created": datetime.now().astimezone().isoformat(timespec="seconds")}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)
    os.chmod(p, 0o600)
