"""Safety checks that must pass before a database client can be invoked."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run_script(
    script: str, *args: str, database: str = "production"
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PATH": "/usr/bin:/bin",
        "PGHOST": "unused.invalid",
        "PGUSER": "test",
        "PGPASSWORD": "test",
        "PGDATABASE": database,
        "PGSSLMODE": "disable",
    }
    return subprocess.run(
        ["/bin/sh", str(ROOT / "scripts" / script), *args],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_backup_never_overwrites_existing_file(tmp_path: Path) -> None:
    backup = tmp_path / "existing.dump"
    backup.write_bytes(b"preserve this backup")
    result = run_script("backup-database.sh", str(backup))
    assert result.returncode != 0
    assert "must not exist" in result.stderr
    assert backup.read_bytes() == b"preserve this backup"


def test_restore_refuses_non_disposable_database(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"fixture")
    result = run_script("restore-database.sh", str(backup))
    assert result.returncode != 0
    assert "restricted to new spendgraph_restore_" in result.stderr


def test_smoke_requires_https() -> None:
    result = run_script("smoke-deployment.sh", "http://unused.invalid")
    assert result.returncode != 0
    assert "requires HTTPS" in result.stderr
