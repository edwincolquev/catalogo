"""Entrega a Codex el token temporal de Supabase sin guardarlo en config.toml."""

import json
from pathlib import Path

env_file = Path(__file__).resolve().parents[1] / ".env"
token = None
for line in env_file.read_text(encoding="utf-8-sig").splitlines():
    if line.startswith("SUPABASE_ACCESS_TOKEN="):
        token = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not token:
    raise SystemExit("Falta SUPABASE_ACCESS_TOKEN en C:/Catalogo/.env")
print(json.dumps({"Authorization": f"Bearer {token}"}))
