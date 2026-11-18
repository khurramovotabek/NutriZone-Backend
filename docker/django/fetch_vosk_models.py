"""Build step (docker/django/Dockerfile, stage voskmodels): download the offline speech models used by
apps/assistant/infrastructure/stt.py from the official Vosk mirror, verify each by SHA-256, unpack into /opt/vosk."""

import hashlib
import io
import urllib.request
import zipfile

MODELS = {
    "vosk-model-small-uz-0.22": "ffb77328df64f222a3fac6e368e0baff9dc1258f11b6b5ca5deaa82e5f688e6a",
    "vosk-model-small-ru-0.22": "961d5ff98a17f4aa6de69864d0aa71fa5bac682301d2b5d17a3f24c5c99a46d4",
    "vosk-model-small-en-us-0.15": "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498",
}

for name, sha in MODELS.items():
    data = urllib.request.urlopen(f"https://alphacephei.com/vosk/models/{name}.zip", timeout=900).read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        raise SystemExit(f"{name}: sha256 {got} != {sha}")
    zipfile.ZipFile(io.BytesIO(data)).extractall("/opt/vosk")
    print("vosk model ok:", name)
