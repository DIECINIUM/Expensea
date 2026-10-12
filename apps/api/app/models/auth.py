"""Server-owned identities, opaque sessions and single-use OAuth transactions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AuthIdentity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(255))


class AuthSession(CreatedAtMixin, Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OAuthState(CreatedAtMixin, Base):
    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(20))
    browser_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    nonce: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GmailCredential(CreatedAtMixin, Base):
    __tablename__ = "gmail_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    refresh_ciphertext: Mapped[str | None] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(120))
    scopes: Mapped[str] = mapped_column(Text)
    account_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="connected")
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
