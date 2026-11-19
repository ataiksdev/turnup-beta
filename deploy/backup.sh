#!/bin/sh
# Nightly database backup (runs in the "backup" service of docker-compose.yml).
# Writes /backups/turnup-YYYY-MM-DD.sql.gz once a day and deletes dumps older than
# BACKUP_KEEP_DAYS. Restore one with deploy/oracle/README.md -> "Restore a backup".
set -eu
KEEP="${BACKUP_KEEP_DAYS:-14}"

backup() {
  file="/backups/turnup-$(date -u +%Y-%m-%d).sql.gz"
  # Write to a temp file first so a failed dump never replaces a good one.
  if pg_dump --no-owner --no-privileges | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup: wrote $file ($(du -h "$file" | cut -f1))"
  else
    rm -f "$file.tmp"
    echo "backup: FAILED" >&2
  fi
  find /backups -name 'turnup-*.sql.gz' -mtime +"$KEEP" -print -delete | sed 's/^/backup: removed /'
}

backup                      # once at start-up, so a fresh deploy has a backup right away
while true; do
  sleep 86400
  backup
done
