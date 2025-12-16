# Data Safety Guide

## ⚠️ Important: Protecting Your Media Files

This application **NEVER deletes media files** - it only reads them for streaming. However, when setting up storage on TrueNAS, you need to be careful about ZFS dataset creation.

## The Risk: ZFS Dataset Creation

When you create a ZFS dataset at a path where a directory with files already exists, the dataset will replace the mount point, effectively hiding your existing files. **This is why the setup script now checks for existing data before creating datasets.**

## What the Setup Script Does Now

The `truenas-setup.sh` script has been updated with safety checks:

1. **Checks for existing data** before creating any ZFS dataset
2. **Warns you** if it finds a directory with files
3. **Asks for confirmation** before proceeding
4. **Aborts** if you don't explicitly confirm

## Best Practices

### If You Already Have Media Files

1. **Don't create a new dataset** over your existing media location
2. **Use your existing media path** in `docker-compose.truenas.yml`
3. **Skip the media dataset creation** in the setup script if prompted

### Example: Using Existing Samba Share

If your media is already on a Samba share at `/mnt/blackhole/shared/media`:

```yaml
# In docker-compose.truenas.yml
volumes:
  - /mnt/blackhole/shared/media:/media/tvchannel:ro  # Use existing path
```

**Don't create** `blackhole/media/tv` dataset - just use the existing path!

### Setting Up Automatic Snapshots

To protect against accidental data loss, set up automatic ZFS snapshots in TrueNAS:

1. Go to **Storage → Periodic Snapshot Tasks**
2. Create a task for your media datasets (e.g., `blackhole/media`)
3. Set frequency: Daily (or more often)
4. Keep multiple snapshots: 7 daily, 4 weekly, 12 monthly

This way, if something goes wrong, you can restore from a snapshot.

## What Happened Before

Previously, the setup script would create ZFS datasets without checking for existing data. This could replace existing directories and hide files. **This has been fixed** - the script now always checks first.

## Recovery

If you lose data:
1. **Check ZFS snapshots** first (if automatic snapshots are enabled)
2. Check external backups (external drives, cloud backups)
3. Check if files are in a different location

## Questions?

If you're unsure about your setup, the script will warn you. Always read the warnings carefully before proceeding.

