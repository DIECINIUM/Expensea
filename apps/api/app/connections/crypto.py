"""Environment-supplied keyring; active key writes, retained key IDs allow rotation."""

import json

from cryptography.fernet import Fernet, InvalidToken

from app.auth.session import AuthError
from app.core.config import Settings


class TokenVault:
    def __init__(self, settings: Settings) -> None:
        self.active_id = settings.token_encryption_active_key_id
        self.keys = json.loads(settings.token_encryption_keys)

    def encrypt(self, token: str) -> tuple[str, str]:
        try:
            ciphertext = Fernet(self.keys[self.active_id].encode("ascii")).encrypt(
                token.encode("utf-8")
            )
            return self.active_id, ciphertext.decode("ascii")
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthError("TOKEN_KEY_UNAVAILABLE", 503) from exc

    def decrypt(self, key_id: str, ciphertext: str) -> str:
        try:
            return (
                Fernet(self.keys[key_id].encode("ascii"))
                .decrypt(ciphertext.encode("ascii"))
                .decode("utf-8")
            )
        except (KeyError, InvalidToken, ValueError, UnicodeError) as exc:
            raise AuthError("TOKEN_KEY_UNAVAILABLE", 503) from exc
