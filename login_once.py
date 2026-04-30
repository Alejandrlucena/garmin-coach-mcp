from __future__ import annotations

import getpass
from pathlib import Path

from garminconnect import Garmin


def main() -> None:
    email = input("Email Garmin: ").strip()
    password = getpass.getpass("Contraseña Garmin: ")

    token_dir = Path.home() / ".garminconnect"
    token_dir.mkdir(parents=True, exist_ok=True)

    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Código MFA que te llegue por email: ").strip(),
    )

    client.login(str(token_dir))

    token_file = token_dir / "garmin_tokens.json"
    print("\nLogin OK.")
    print(f"Archivo de tokens: {token_file}\n")
    print("Pega este JSON entero en Railway como GARMIN_TOKENS_JSON:\n")
    print(token_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
