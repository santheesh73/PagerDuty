"""scripts/backup.sh and scripts/restore.sh: rotation, verification, failure behaviour, upload.

These run the real scripts against the test database with the real pg_dump/pg_restore. The
full end-to-end proof (seed, back up, restore elsewhere, compare, boot the API) is
scripts/backup_drill.sh, run as `make backup-drill` and by a CI job.
"""

import os
import shutil
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(__file__).resolve().parents[4]
BACKUP = ROOT / "scripts" / "backup.sh"
RESTORE = ROOT / "scripts" / "restore.sh"

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not (shutil.which("pg_dump") and shutil.which("pg_restore") and BACKUP.exists()),
        reason="needs pg_dump/pg_restore on PATH and the repo's scripts/",
    ),
]


def db_url() -> str:
    cfg = settings.DATABASES["default"]
    auth = f"{cfg['USER']}:{cfg['PASSWORD']}"
    return f"postgres://{auth}@{cfg['HOST']}:{cfg['PORT'] or 5432}/{cfg['NAME']}"


def run(script: Path, *args: str, env: dict | None = None, cwd: Path | None = None):
    full = {**os.environ, "PATH": os.environ["PATH"], **(env or {})}
    return subprocess.run(
        ["bash", str(script), *args],
        env=full,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def backup(tmp_path: Path, stamp: str, **env: str):
    return run(
        BACKUP,
        env={"DATABASE_URL": db_url(), "BACKUP_DIR": str(tmp_path), "BACKUP_STAMP": stamp, **env},
    )


def names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.glob("pulse-*.dump"))


def test_backup_writes_a_verified_checksummed_dump(tmp_path: Path) -> None:
    result = backup(tmp_path, "20260101T000000Z")
    assert result.returncode == 0, result.stderr
    dump = tmp_path / "daily" / "pulse-20260101T000000Z.dump"
    assert dump.stat().st_size > 0
    assert (tmp_path / "daily" / (dump.name + ".sha256")).exists()
    assert not list(tmp_path.glob(".*partial")), "no partial file may be left behind"
    # readable by pg_restore, which is what verification means
    assert (
        subprocess.run(
            ["pg_restore", "--list", str(dump)], capture_output=True, check=False
        ).returncode
        == 0
    )


def _iso_weekday_today() -> int:
    return int(subprocess.run(["date", "-u", "+%u"], capture_output=True, text=True).stdout)


@pytest.mark.parametrize("weekly_day", ["today", "another day"])
def test_a_first_backup_succeeds_whatever_the_weekday(tmp_path: Path, weekly_day: str) -> None:
    """On any day but the weekly one `weekly/` stays empty. Rotating it once failed the whole
    script (`ls` on an empty directory exits 2 under pipefail), after the dump was written but
    before the off-site upload and the heartbeat ping: every non-Sunday on a fresh install.
    Found by the final audit; CI and the earlier runs had only ever happened to run on a Sunday."""
    today = _iso_weekday_today()
    dow = today if weekly_day == "today" else today % 7 + 1
    result = backup(tmp_path, "20260105T000000Z", BACKUP_WEEKLY_DOW=str(dow))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "daily" / "pulse-20260105T000000Z.dump").exists()
    assert bool(list((tmp_path / "weekly").glob("pulse-*.dump"))) is (weekly_day == "today")


def test_rotation_keeps_the_newest_n_dumps_and_their_checksums(tmp_path: Path) -> None:
    for day in range(1, 6):
        assert backup(tmp_path, f"2026010{day}T000000Z", BACKUP_RETAIN_DAILY="2").returncode == 0
    assert names(tmp_path / "daily") == [
        "pulse-20260104T000000Z.dump",
        "pulse-20260105T000000Z.dump",
    ]
    assert sorted(p.name for p in (tmp_path / "daily").glob("*.sha256")) == [
        "pulse-20260104T000000Z.dump.sha256",
        "pulse-20260105T000000Z.dump.sha256",
    ]


def test_weekly_copy_is_made_only_on_the_configured_weekday(tmp_path: Path) -> None:
    today = subprocess.run(
        ["date", "-u", "+%u"], capture_output=True, text=True, check=True
    ).stdout.strip()
    other = "1" if today != "1" else "2"
    backup(tmp_path, "20260201T000000Z", BACKUP_WEEKLY_DOW=other)
    assert names(tmp_path / "weekly") == []
    backup(tmp_path, "20260202T000000Z", BACKUP_WEEKLY_DOW=today)
    assert names(tmp_path / "weekly") == ["pulse-20260202T000000Z.dump"]


def test_a_failed_backup_deletes_nothing_and_does_not_ping_the_monitor(tmp_path: Path) -> None:
    for day in (1, 2):
        backup(tmp_path, f"2026010{day}T000000Z", BACKUP_RETAIN_DAILY="1")
    survivors = names(tmp_path / "daily")
    pings: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            pings.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/beat"
        bad = run(
            BACKUP,
            env={
                "DATABASE_URL": "postgres://nobody:x@127.0.0.1:1/none",
                "BACKUP_DIR": str(tmp_path),
                "BACKUP_RETAIN_DAILY": "1",
                "BACKUP_HEARTBEAT_URL": url,
            },
        )
        assert bad.returncode != 0
        assert names(tmp_path / "daily") == survivors, (
            "a failing job must not rotate away the last good dump"
        )
        assert pings == []
        good = backup(
            tmp_path, "20260103T000000Z", BACKUP_RETAIN_DAILY="1", BACKUP_HEARTBEAT_URL=url
        )
        assert good.returncode == 0, good.stderr
        assert pings == ["/beat"]
    finally:
        server.shutdown()


@pytest.fixture
def fake_aws(tmp_path: Path) -> tuple[Path, Path]:
    """An `aws` on PATH that records its arguments and the credentials it was given."""
    bin_dir, log = tmp_path / "bin", tmp_path / "aws.log"
    bin_dir.mkdir()
    exe = bin_dir / "aws"
    exe.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {log}\n'
        'echo "key=$AWS_ACCESS_KEY_ID secret=$AWS_SECRET_ACCESS_KEY'
        f' region=$AWS_DEFAULT_REGION" >> {log}\n'
        '[ -z "$FAKE_AWS_FAIL" ] || exit 1\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log


def test_upload_goes_to_the_configured_s3_compatible_bucket(tmp_path: Path, fake_aws) -> None:
    bin_dir, log = fake_aws
    result = backup(
        tmp_path / "out",
        "20260301T000000Z",
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        BACKUP_S3_BUCKET="vault",
        BACKUP_S3_PREFIX="prod",
        BACKUP_S3_ENDPOINT="https://r2.example.com",
        BACKUP_S3_REGION="auto",
        BACKUP_S3_SSE="AES256",
        BACKUP_S3_ACCESS_KEY_ID="AKIATEST",
        BACKUP_S3_SECRET_ACCESS_KEY="s3cr3t",
    )
    assert result.returncode == 0, result.stderr
    first, second = log.read_text().splitlines()
    assert first.startswith("s3 cp ")
    assert first.endswith(
        "s3://vault/prod/daily/pulse-20260301T000000Z.dump --only-show-errors "
        "--endpoint-url https://r2.example.com --sse AES256"
    )
    assert second == "key=AKIATEST secret=s3cr3t region=auto"
    assert "s3cr3t" not in result.stdout + result.stderr


def test_a_failed_upload_fails_the_job_so_the_monitor_goes_quiet(tmp_path: Path, fake_aws) -> None:
    bin_dir, _ = fake_aws
    result = backup(
        tmp_path / "out",
        "20260301T000000Z",
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        BACKUP_S3_BUCKET="vault",
        FAKE_AWS_FAIL="1",
    )
    assert result.returncode != 0


def test_restore_refuses_a_corrupt_dump_and_the_live_database(tmp_path: Path) -> None:
    assert backup(tmp_path, "20260401T000000Z").returncode == 0
    dump = tmp_path / "daily" / "pulse-20260401T000000Z.dump"

    live = run(RESTORE, str(dump), db_url(), env={"DATABASE_URL": db_url()})
    assert live.returncode == 2
    assert "CONFIRM_OVERWRITE" in live.stderr

    dump.write_bytes(
        dump.read_bytes()[:-50] + b"corrupted-tail-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    )
    bad = run(RESTORE, str(dump), "postgres://x:y@127.0.0.1:1/none")
    assert bad.returncode == 1
    assert "checksum mismatch" in bad.stderr


def test_a_weekly_copy_that_fails_halfway_leaves_nothing_that_looks_like_a_backup(
    tmp_path: Path,
) -> None:
    """Disk full while copying to weekly/ once left a truncated dump and an empty checksum under
    their final names; retention then counted them and pushed out a good weekly copy."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    cp = fake_bin / "cp"
    cp.write_text(
        "#!/bin/sh\n"
        "for last; do :; done\n"
        '[ -d "$last" ] && last="$last/$(basename "$1")"  # like cp: into a directory\n'
        'head -c 10 "$1" > "$last"  # the disk fills after ten bytes\n'
        'echo "cp: No space left on device" >&2\nexit 1\n'
    )
    cp.chmod(0o755)
    out = tmp_path / "out"
    result = run(
        BACKUP,
        env={
            "DATABASE_URL": db_url(),
            "BACKUP_DIR": str(out),
            "BACKUP_STAMP": "20260105T000000Z",
            "BACKUP_WEEKLY_DOW": str(_iso_weekday_today()),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
        },
    )
    assert result.returncode != 0
    assert list((out / "weekly").iterdir()) == [], "no file, partial or final, may be left"
    assert (out / "daily" / "pulse-20260105T000000Z.dump").stat().st_size > 10
