from ipaddress import IPv4Address, IPv4Network
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Port = Annotated[int, Field(ge=1, le=65535)]
hasher = PasswordHasher()


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAPC_", env_file=".env", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8080
    admin_user: str = "admin"
    admin_password: SecretStr
    session_ttl: int = Field(default=28800, ge=60, le=604800)
    cookie_secure: bool = False  # Set True when served over HTTPS.
    database_url: str = "sqlite:///./mapc.db"
    usernames: set[str] = Field(default_factory=set)
    passwords: set[str] = Field(default_factory=set)
    excluded_ips: set[IPv4Address] = Field(default_factory=set)

    @staticmethod
    def hash_password(password: str) -> str:
        return hasher.hash(password)

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        try:
            return hasher.verify(stored_hash, password)
        except VerifyMismatchError:
            return False


class ScanConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAPC_SCAN_", env_file=".env", extra="ignore"
    )

    networks: set[IPv4Network] = Field(default_factory=set)
    ports: set[Port] = Field(default_factory=set)
    scanner_timeout: float = Field(default=1, gt=0)
    camera_timeout: float = Field(default=15, gt=0)
    camera_concurrency: int = Field(default=32, ge=1, le=32)
    concurrency: int = Field(default=64, ge=1, le=64)


if __name__ == "__main__":
    ...
