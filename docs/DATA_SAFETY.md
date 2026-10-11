# Data safety

What happens to the data if the database dies, a deploy goes wrong, or the tables grow for years.
Everything claimed here was run; the numbers say where and how.

## Backups

`scripts/backup.sh` runs `pg_dump -Fc`, then **reads the dump back** (`pg_restore --list`), writes a
SHA-256 beside it, rotates (default 7 daily + 4 weekly) and, if `BACKUP_S3_BUCKET` is set, uploads to an
S3-compatible bucket with the `aws` CLI (`BACKUP_S3_ENDPOINT` for R2, B2, MinIO, Wasabi...). It
rotates **only after** a verified new dump exists, so a job that keeps failing never deletes your last
good backup, and a failed run does not ping `BACKUP_HEARTBEAT_URL`, so a monitor notices when backups
stop.

In the prod-like compose stack the `backup` service runs it at start and every
`BACKUP_INTERVAL_SECONDS` (default 24 h) into the `backups-prod` volume. Its health check goes
unhealthy when the last success is older than twice the interval. On a bare host, cron works the same:

```cron
17 3 * * *  DATABASE_URL=postgres://... BACKUP_DIR=/srv/pulse/backups /srv/pulse/scripts/backup.sh
```

| Variable | Default | |
|---|---|---|
| `BACKUP_DIR` | `./backups` | `daily/` and `weekly/` live below it |
| `BACKUP_RETAIN_DAILY`, `BACKUP_RETAIN_WEEKLY`, `BACKUP_WEEKLY_DOW` | 7, 4, 7 (Sunday) | local rotation |
| `BACKUP_S3_BUCKET`, `_PREFIX`, `_ENDPOINT`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY`, `_SSE` | unset (no upload) | remote retention is the bucket's lifecycle rule |
| `BACKUP_HEARTBEAT_URL` | unset | pinged after a fully successful run |

Dumps contain incident history, user emails and password hashes. Treat them like the database:
restrict the directory, use `BACKUP_S3_SSE=AES256` (or your provider's default encryption), and use a
bucket credential that can write but not delete.

## Restoring

```bash
scripts/restore.sh backups/daily/pulse-<stamp>.dump postgres://user:pass@host:5432/scratch_db
```

One transaction (a failed restore leaves the target as it was), checksum verified first, and it
**refuses to overwrite the live `DATABASE_URL`** unless `CONFIRM_OVERWRITE=yes`. Restore into a
scratch database, look, then repoint the app or `ALTER DATABASE ... RENAME`.

## The drill: proof that the backups restore

`make backup-drill` (also a CI job, `Backup drill`) does, against any Postgres you can create databases in:

1. migrate and seed a scratch database (24 tables, 400 incidents);
2. `backup.sh` it;
3. `restore.sh` into a second scratch database;
4. compare **row counts of every table, all 88 index definitions, all 92 constraint definitions, and every
   sequence value** (a stale sequence would hand out a duplicate incident number);
5. boot the API against the restored copy: `/readyz` is 200, the demo admin logs in, the API lists all
   400 incidents, and a **new alert is accepted** (which exercises the partial unique index
   `uniq_open_incident_per_dedup_key` and the sequences).

It drops both databases afterwards, even on failure.

## RPO and RTO, honestly

- **RPO (data you can lose): up to one backup interval.** Default 24 hours. Every alert, acknowledgement
  and resolve since the last dump is gone after a restore. Lower `BACKUP_INTERVAL_SECONDS` (hourly is
  cheap at this size) to shrink it. There is **no WAL archiving / point-in-time recovery**; a managed
  Postgres with PITR (Neon, Supabase, RDS) gives that and is the better answer if hours of loss matter.
- **RTO (time to be back):** the restore itself is quick. Measured on one machine (Postgres 16, local
  disk, no network): the seeded 400-incident database restores in about 1 s; a synthetic 330 MB database
  (100,400 incidents, 300,923 alerts) dumped in 2.4 s (8 MB, it compresses well) and restored in 6.0 s.
  Real RTO is dominated by what the drill cannot measure: noticing, provisioning a database and
  repointing the app, typically minutes to an hour for one person. Those numbers are not a capacity
  claim for other hardware.
- Redis holds nothing that needs restoring (it is a disposable broker). After a restore the
  Beat sweepers re-drive any escalation or page that was in flight.
- **Not verified:** an upload to a real S3-compatible service (tested with a stand-in `aws` that records
  its arguments), cross-major-version restores, and encrypted-at-rest bucket behaviour.

## Migrations on a live database

Rules (also in [DECISIONS.md](DECISIONS.md#data-safety-production-readiness-phase-2)):

1. **Expand, then contract.** Ship additive changes first (new nullable column, new table, new index);
   deploy code that works with both shapes; only in a *later* release remove the old column, constraint
   or code path. Never rename or drop in the same release that stops using the thing.
2. New `NOT NULL` columns need a default (or a backfill in a prior release); big-table `CHECK` and
   `FOREIGN KEY` constraints should be added `NOT VALID` and validated separately; indexes on busy
   tables are created `CONCURRENTLY` (`AddIndexConcurrently`, non-atomic migration).
3. Data migrations are idempotent and batched.

`django-migration-linter` enforces the mechanical part in CI (`make lint-migrations`): dropping or
renaming columns/tables, adding non-null columns without defaults, and non-reversible operations fail
the build. Shown working: a throwaway `RemoveField` migration is rejected (`DROPPING columns`), the
real ones pass 11/11.

**Concurrent `migrate` was not safe, and is now.** Four `manage.py migrate` processes started at once
on a fresh database failed 3 out of 4, every round (`duplicate key value violates unique constraint
"pg_type_typname_nsp_index"`), which is exactly what starting several API replicas together does. The
container entrypoint now runs `manage.py migrate_safely`, which holds a Postgres advisory lock while it
migrates, so the others wait and find nothing left to do. Waiters poll `pg_try_advisory_lock` rather
than block: a blocked lock call is an open transaction, and `CREATE INDEX CONCURRENTLY` waits for every
open transaction, so the first version deadlocked as soon as a migration built an index concurrently
(found when the channels phase added one; reproduced, then fixed). A test starts four at once and requires four
successes (`test_concurrent_migrate_safely_on_a_fresh_database_all_succeed`); removing the lock makes it fail.
The migration itself runs with `lock_timeout` 10 s, so one that cannot get its table lock fails and the
container restarts instead of queueing behind a long transaction and blocking all traffic behind itself.

## Retention

`RETENTION_DAYS` (default **0 = keep everything**). When set, a daily Beat task deletes **resolved**
incidents resolved more than N days ago together with their timeline, notifications and alerts (alerts
are `SET_NULL` on the incident FK, so they are deleted explicitly), plus alerts that old that never joined an
incident. **Open incidents are never deleted**, however old. It works in batches of 500 so no
transaction is long. The same task clears expired sessions (housekeeping, always on).

Analytics (MTTA, MTTR, trends) are computed from incidents, so purging history shortens the window they
can show. Pick N to match the longest window you want to report on.

## Limits that stop one bad thing wedging everything

| Setting | Value | Why |
|---|---|---|
| `statement_timeout` (`DB_STATEMENT_TIMEOUT_MS`) | 15 s | every request and task here is small indexed work; a runaway query is cancelled, not left pinning a worker. Migrations run with it off |
| `lock_timeout` (`DB_LOCK_TIMEOUT_MS`) | 5 s | give up waiting for a row/table lock instead of queueing forever |
| `idle_in_transaction_session_timeout` (`DB_IDLE_IN_TX_TIMEOUT_MS`) | 60 s | a client idle inside a transaction is holding locks; delivery deliberately sends with no transaction open, so no legitimate path idles |
| `CONN_MAX_AGE` (`DB_CONN_MAX_AGE`) | 60 s, health-checked | avoids a connection handshake per request; about 10 persistent connections at default sizing |
| Celery `acks_late` + `reject_on_worker_lost` | on | a worker that dies mid-task redelivers instead of losing a page |
| Celery `visibility_timeout` | 3600 s (explicit) | only needs to exceed the longest ETA wait; dead-worker recovery relies on the 60 s stuck-notification sweep, not on redelivery |
| Celery task time limit | 60 s soft, 90 s hard | a wedged task must free its worker slot |

Set the three `DB_*_MS` variables to `0` behind a transaction-mode pooler (PgBouncer, Neon's pooled
endpoint): they reject startup options.
