#!/usr/bin/env python3
"""
Compile locale/*/LC_MESSAGES/django.po -> django.mo without GNU gettext (the Docker image has no msgfmt).

    python scripts/compile_messages.py            # all locales
    python scripts/compile_messages.py uz ru      # selected

Rules: `#, fuzzy` entries are skipped (as msgfmt does); for `uz` an empty msgstr falls back to the msgid, because
the project's Uzbek source strings must never fall through to another catalog. Restart the web/celery processes
afterwards -- Django caches catalogs per process.
"""
from __future__ import annotations

import ast
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "locale"


def _unquote(chunks: list[str]) -> str:
    return "".join(ast.literal_eval(c) for c in chunks)


def parse(path: pathlib.Path) -> dict[str, str]:
    """Entries are separated by blank lines; `#` comment lines are ignored except the fuzzy flag."""
    entries: dict[str, str] = {}
    uz = path.parts[-3] == "uz"

    def flush(entry: dict, fuzzy: bool) -> None:
        if "msgid" not in entry:
            return
        msgid = _unquote(entry["msgid"])
        if fuzzy and msgid:
            return
        if "msgid_plural" in entry:
            forms = [_unquote(entry[k]) for k in sorted((k for k in entry if k.startswith("msgstr[")), key=lambda k: int(k[7:-1]))]
            if not any(forms):
                return
            key, value = f"{msgid}\0{_unquote(entry['msgid_plural'])}", "\0".join(forms)
        else:
            value = _unquote(entry.get("msgstr", ['""'])) or (msgid if uz else "")
            if not value:
                return
            key = msgid
        if "msgctxt" in entry:
            key = f"{_unquote(entry['msgctxt'])}\x04{key}"
        entries[key] = value

    entry: dict = {}
    fuzzy = False
    key = None
    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if not line:
            flush(entry, fuzzy)
            entry, fuzzy, key = {}, False, None
        elif line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
        elif line.startswith('"'):
            if key is not None:
                entry[key].append(line)
        else:
            key, _, rest = line.partition(" ")
            entry[key] = [rest]
    return entries


def write_mo(entries: dict[str, str], out: pathlib.Path) -> None:
    keys = sorted(entries)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(entries[k].encode() + b"\0" for k in keys)
    n = len(keys)
    key_start = 7 * 4 + 16 * n
    val_start = key_start + len(ids)
    koffsets, voffsets, ko, vo = [], [], 0, 0
    for k in keys:
        kb, vb = k.encode(), entries[k].encode()
        koffsets += [len(kb), key_start + ko]
        voffsets += [len(vb), val_start + vo]
        ko += len(kb) + 1
        vo += len(vb) + 1
    header = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    tmp = out.with_suffix(".mo.tmp")
    tmp.write_bytes(header + struct.pack(f"{2 * n}i", *koffsets) + struct.pack(f"{2 * n}i", *voffsets) + ids + strs)
    tmp.replace(out)


def main(locales: list[str]) -> None:
    for po in sorted(ROOT.glob("*/LC_MESSAGES/django.po")):
        if locales and po.parts[-3] not in locales:
            continue
        entries = parse(po)
        write_mo(entries, po.with_suffix(".mo"))
        print(f"{po.parts[-3]}: {len(entries)} messages -> {po.with_suffix('.mo').relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main(sys.argv[1:])
