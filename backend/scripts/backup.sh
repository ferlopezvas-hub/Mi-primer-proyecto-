#!/bin/sh
# Copia de seguridad de PostgreSQL con rotación.
#   BACKUP_DIR (por defecto /backups), BACKUP_KEEP_DAYS (por defecto 14)
#   Opcional: BACKUP_S3_URI=s3://bucket/ruta  (requiere aws-cli configurado) para copia externa.
set -eu
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
URL="$(echo "$DATABASE_URL" | sed 's/+psycopg//')"
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/sportai-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --dbname="$URL" --file="$FILE"
pg_restore --list "$FILE" > /dev/null   # verifica que el fichero es legible
echo "Copia creada: $FILE ($(du -h "$FILE" | cut -f1))"
find "$BACKUP_DIR" -name 'sportai-*.dump' -mtime +"$KEEP" -delete
if [ -n "${BACKUP_S3_URI:-}" ]; then aws s3 cp "$FILE" "$BACKUP_S3_URI/"; fi
# Restaurar:  pg_restore --clean --if-exists --no-owner --dbname="$URL" fichero.dump
