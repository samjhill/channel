# Using Existing Samba Share with TrueNAS Scale

If your media files are already set up as a Samba share on TrueNAS Scale, you can use that share directly without copying files or creating a new dataset.

## Finding Your Samba Share Path

### Method 1: TrueNAS Web UI

1. Log into TrueNAS Scale web interface
2. Navigate to **Shares** → **SMB Shares**
3. Find your media share in the list
4. Click on it to view details
5. Note the **Path** field - this is the dataset path you need

Example paths:
- `/mnt/tank/media`
- `/mnt/pool/media/tv`
- `/mnt/tank/shared/media`

### Method 2: Command Line

```bash
# SSH into TrueNAS Scale
ssh root@your-truenas-ip

# List all Samba shares and their paths
midclt call smb.shares.query | grep -E "(name|path)"

# Or list datasets that might contain media
zfs list | grep -i media
```

## Updating docker-compose.truenas.yml

Once you know your Samba share's dataset path, update the media volume mount:

```yaml
volumes:
  # Replace with your actual Samba share dataset path
  - /mnt/tank/media:/media/tvchannel:ro
  # ... other volumes
```

**Important**: Use the dataset path (e.g., `/mnt/tank/media`), not the SMB share name or network path.

## Example Configuration

If your Samba share is configured as:
- **Share Name**: `media`
- **Path**: `/mnt/tank/shared/media`
- **Pool**: `tank`

Then your `docker-compose.truenas.yml` should have:

```yaml
volumes:
  - /mnt/tank/shared/media:/media/tvchannel:ro
  - /mnt/tank/apps/tvchannel/assets:/app/assets
  - /mnt/tank/apps/tvchannel/config:/app/config
  - /mnt/tank/apps/tvchannel/hls:/app/hls
```

## Permissions

The Docker container runs as root by default, so it should have access to your Samba share dataset. However, if you encounter permission issues:

1. **Check dataset permissions**:
   ```bash
   ls -la /mnt/tank/media  # or your media path
   ```

2. **Ensure dataset is readable**:
   ```bash
   chmod -R 755 /mnt/tank/media
   ```

3. **If using ACLs**, ensure the dataset allows container access:
   - Go to **Storage** → **Pools** → Select your dataset
   - Check **ACL** settings
   - Ensure read permissions are set appropriately

## Verifying Access After Deployment

After deploying the container, verify it can access your media:

```bash
# Check if media directory is mounted correctly
docker exec tvchannel ls -la /media/tvchannel

# Should show your media files/folders
# Example output:
# drwxr-xr-x  root root  Show Name/
# drwxr-xr-x  root root  Another Show/
```

If you see your media files, the mount is working correctly!

## Troubleshooting

### Container Can't See Media Files

1. **Verify the path exists**:
   ```bash
   # On TrueNAS host
   ls -la /mnt/tank/media  # or your path
   ```

2. **Check volume mount**:
   ```bash
   docker inspect tvchannel | grep -A 10 Mounts
   ```

3. **Test from container**:
   ```bash
   docker exec tvchannel ls -la /media/tvchannel
   ```

### Permission Denied Errors

If you see permission errors:

1. **Check dataset permissions**:
   ```bash
   ls -ld /mnt/tank/media
   ```

2. **Check if dataset has ACL restrictions**:
   - Go to **Storage** → **Pools** → Select dataset
   - Review ACL settings

3. **Temporarily test with wider permissions** (for testing only):
   ```bash
   chmod -R 755 /mnt/tank/media
   ```

### Samba Share Path vs Dataset Path

**Important distinction**:
- **Samba Share Path**: The dataset path (e.g., `/mnt/tank/media`) - Use this in docker-compose
- **SMB Network Path**: `\\truenas-ip\media` or `smb://truenas-ip/media` - Don't use this
- **Share Name**: Just the name like `media` - Don't use this

Always use the **dataset path** shown in the Samba share configuration.

## Benefits of Using Existing Samba Share

- ✅ No need to copy or move media files
- ✅ Media remains accessible via SMB/CIFS for other devices
- ✅ Single source of truth for your media
- ✅ No duplicate storage required
- ✅ Changes to media (add/remove files) are immediately available

## Next Steps

1. Find your Samba share path using the methods above
2. Update `docker-compose.truenas.yml` with the correct path
3. Deploy the container
4. Verify media access as shown above
5. Start streaming!

For more details, see `TRUENAS_QUICK_START.md` and `TRUENAS_SCALE_DEPLOYMENT.md`.


