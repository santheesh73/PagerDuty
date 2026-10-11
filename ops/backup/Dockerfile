# Scheduled database backups: pg_dump (same major version as the db service) + aws CLI for
# S3-compatible upload + curl for the dead-man's-switch ping. Build context is the repo root.
FROM postgres:17-alpine
RUN apk add --no-cache bash curl aws-cli \
    && adduser -D -u 10001 backup \
    && mkdir /backups && chown backup /backups
COPY scripts/backup.sh /usr/local/bin/backup.sh
COPY ops/backup/run.sh /usr/local/bin/run-backups.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/run-backups.sh
USER backup
ENV BACKUP_DIR=/backups
ENTRYPOINT ["/usr/local/bin/run-backups.sh"]
