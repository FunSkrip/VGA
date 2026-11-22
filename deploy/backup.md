# Encrypted database backups

Default locations:

```text
D:\VKR_YOLO_backups\vga-YYYYMMDDTHHMMSSZ.db.vgaenc
D:\VKR_key_backup\backup-keyring.json
```

The keyring is deliberately outside the project directory. Keep a secure copy of
it somewhere else: without the key, an encrypted backup cannot be restored.

## 1. Create the keyring once

```powershell
cd D:\VKR_YOLO
.\venv\Scripts\python.exe tools\backup_db.py --init-keyring
```

Do not commit the keyring to Git. Restrict access to your Windows account.

## 2. Create a backup

```powershell
.\venv\Scripts\python.exe tools\backup_db.py
```

The command:

- uses the SQLite online backup API;
- runs `PRAGMA integrity_check`;
- encrypts the snapshot with AES-256-GCM;
- writes only the encrypted `.vgaenc` file;
- removes backups older than 15 days, keeping the newest one.

## 3. Verify a backup

```powershell
.\venv\Scripts\python.exe tools\verify_backup.py
```

This decrypts to a temporary file, checks the GCM tag and SHA-256, runs
`PRAGMA integrity_check`, and deletes the temporary plaintext file.

## 4. Restore

Stop the VGA application first. Then:

```powershell
.\venv\Scripts\python.exe tools\restore_db.py --yes
```

By default it uses the newest backup and saves the current database as:

```text
VKR_YOLO.db.pre-restore-YYYYMMDDTHHMMSSZ
```

To choose a specific file:

```powershell
.\venv\Scripts\python.exe tools\restore_db.py --backup "D:\VKR_YOLO_backups\vga-....db.vgaenc" --yes
```

The restore verifies the backup, checks SQLite integrity, replaces the database,
removes stale `-wal`/`-shm` files and prints table counts.

## 5. Daily schedule (Task Scheduler)

Run PowerShell as the Windows account that can read the keyring:

```powershell
$action = New-ScheduledTaskAction `
  -Execute "D:\VKR_YOLO\venv\Scripts\python.exe" `
  -Argument "D:\VKR_YOLO\tools\backup_db.py" `
  -WorkingDirectory "D:\VKR_YOLO"

$trigger = New-ScheduledTaskTrigger -Daily -At 02:00

Register-ScheduledTask `
  -TaskName "VGA DB Backup" `
  -Action $action `
  -Trigger $trigger `
  -Description "Encrypted VGA SQLite backup"
```

Check that the task runs under an account with access to
`D:\VKR_key_backup` and `D:\VKR_YOLO_backups`.

## 6. Retention

`VGA_BACKUP_KEEP_DAYS=15` by default. Override it in `.env` or pass:

```powershell
.\venv\Scripts\python.exe tools\backup_db.py --keep-days 30
```

The newest backup is always kept, even if it is older than the retention limit.

## 7. What is included

The backup contains the whole SQLite database:

- users;
- media metadata;
- audit log.

It does **not** include `processed/` media files. They are protected at rest by
BitLocker, but a separate full media backup would be needed for disaster
recovery of the files themselves.

## 8. WAL note

The backup uses SQLite's online backup API, so it also captures committed data
from `VKR_YOLO.db-wal`. Never copy only `VKR_YOLO.db` while the application is
running.
