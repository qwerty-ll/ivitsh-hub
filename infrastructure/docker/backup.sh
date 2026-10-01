#!/bin/sh
# Nightly copy of the database (pg_dump) and the uploaded files into /backups.
# Runs once a day at BACKUP_HOUR (UTC, default 00 = 03:00 Moscow) and keeps BACKUP_KEEP_DAYS days.
set -u
HOUR="${BACKUP_HOUR:-00}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
DIR=/backups

backup() {
  stamp=$(date -u +%Y%m%d-%H%M)
  if pg_dump -Fc -f "$DIR/db_$stamp.dump.part"; then
    mv "$DIR/db_$stamp.dump.part" "$DIR/db_$stamp.dump"
    echo "backup: database -> db_$stamp.dump"
  else
    rm -f "$DIR/db_$stamp.dump.part"
    echo "backup: pg_dump FAILED" >&2
  fi
  if [ -d /app/data/uploads ]; then
    if tar czf "$DIR/uploads_$stamp.tgz.part" -C /app/data uploads; then
      mv "$DIR/uploads_$stamp.tgz.part" "$DIR/uploads_$stamp.tgz"
      echo "backup: files -> uploads_$stamp.tgz"
    else
      rm -f "$DIR/uploads_$stamp.tgz.part"
      echo "backup: uploads archive FAILED" >&2
    fi
  fi
  find "$DIR" -maxdepth 1 \( -name 'db_*.dump' -o -name 'uploads_*.tgz' \) -mtime +"$KEEP" -delete
}

mkdir -p "$DIR"
[ "${BACKUP_ON_START:-1}" = "1" ] && backup
last=$(date -u +%Y%m%d)
while true; do
  sleep 300
  today=$(date -u +%Y%m%d)
  if [ "$(date -u +%H)" = "$HOUR" ] && [ "$today" != "$last" ]; then
    backup
    last=$today
  fi
done
