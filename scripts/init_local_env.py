"""Create local secrets once, without printing or replacing them."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
try:
    descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print(".env already exists; left unchanged.")
else:
    with os.fdopen(descriptor, "w") as stream:
        stream.write(f"PAW_DB_PASSWORD={secrets.token_hex(24)}\n")
        stream.write(f"N8N_ENCRYPTION_KEY={secrets.token_hex(32)}\n")
    print("Created private .env with random local credentials.")
