# TrueNAS Scale Quick Start Guide

## Prerequisites

- TrueNAS Scale running
- SSH access (or shell access via TrueNAS UI)
- Media files ready to deploy

## Quick Deployment Steps

### 1. Find Your Pool Name

First, identify your pool name (it might be `tank`, `blackhole`, or something else):

```bash
# SSH into TrueNAS Scale
ssh root@your-truenas-ip

# List pools
zpool list

# Or check what's in /mnt
ls -la /mnt/
```

**Important**: `/mnt/apps/applications` is TrueNAS Scale's Kubernetes system directory - don't use this for your app or media!

### 2. Prepare Storage (One-time setup)

**Option A: Using the setup script** (recommended)
```bash
# Clone repository to a user dataset (NOT /mnt/apps/applications)
# Replace 'blackhole' with your actual pool name
cd /mnt/blackhole  # or /mnt/tank, or your pool name
mkdir -p apps
cd apps
git clone https://github.com/samjhill/channel.git tvchannel
cd tvchannel

# Run setup script (update POOL_NAME if needed)
POOL_NAME=blackhole ./truenas-setup.sh  # Replace 'blackhole' with your pool
```

**Option B: Manual setup**
```bash
# Replace 'blackhole' with your actual pool name
POOL_NAME=blackhole  # or 'tank', etc.

# Create datasets for app data
zfs create -p ${POOL_NAME}/apps/tvchannel/assets
zfs create -p ${POOL_NAME}/apps/tvchannel/config
zfs create -p ${POOL_NAME}/apps/tvchannel/hls

# Set permissions
chmod -R 755 /mnt/${POOL_NAME}/apps/tvchannel
chmod -R 777 /mnt/${POOL_NAME}/apps/tvchannel/hls
```

### 3. Find Your Samba Share Path

Since your media files are already on a Samba share, find the dataset path:

1. **Via TrueNAS Web UI**:
   - Go to **Shares** → **SMB Shares**
   - Find your media share
   - Note the **Path** field (e.g., `/mnt/blackhole/media` or `/mnt/tank/shared/media`)
   - This is the dataset path you'll use in docker-compose

2. **Via Command Line**:
   ```bash
   # List all datasets (replace 'blackhole' with your pool)
   zfs list | grep -E "(NAME|media|shared)"
   
   # Or check Samba share configs
   midclt call smb.shares.query | grep -E "(name|path)"
   ```

The path format is: `/mnt/POOL_NAME/DATASET_NAME`

**Example**: If your pool is `blackhole` and your media dataset is `media`, the path would be `/mnt/blackhole/media`

### 4. Update Configuration

Edit `docker-compose.truenas.yml`:

1. **Update media path** (line 17) - Use your Samba share's dataset path:
   ```yaml
   - /mnt/YOUR_POOL/YOUR_MEDIA_DATASET:/media/tvchannel:ro
   ```
   **Example**: If your pool is `blackhole` and media dataset is `media`:
   ```yaml
   - /mnt/blackhole/media:/media/tvchannel:ro
   ```
   **Example**: If your pool is `tank` and media dataset is `shared/media`:
   ```yaml
   - /mnt/tank/shared/media:/media/tvchannel:ro
   ```

2. **Update application paths** (lines 19-21) - Use your pool name:
   ```yaml
   - /mnt/YOUR_POOL/apps/tvchannel/assets:/app/assets
   - /mnt/YOUR_POOL/apps/tvchannel/config:/app/config
   - /mnt/YOUR_POOL/apps/tvchannel/hls:/app/hls
   ```
   **Example** (if pool is `blackhole`):
   ```yaml
   - /mnt/blackhole/apps/tvchannel/assets:/app/assets
   - /mnt/blackhole/apps/tvchannel/config:/app/config
   - /mnt/blackhole/apps/tvchannel/hls:/app/hls
   ```

3. **Update CORS origins** (line 24):
   ```yaml
   - CORS_ORIGINS=http://YOUR_TRUENAS_IP:5174,http://localhost:5174
   ```
   Replace `YOUR_TRUENAS_IP` with your TrueNAS IP address

### 5. Deploy via TrueNAS Apps

1. **Access TrueNAS Web UI**
   - Navigate to `http://your-truenas-ip`
   - Log in

2. **Install Custom App**
   - Go to **Apps** → **Discover Apps**
   - Click **⋮** (three dots) → **Install via YAML**

3. **Configure App**
   - **Name**: `tvchannel`
   - **Custom Config**: Copy contents of `docker-compose.truenas.yml`
   - **Storage**: Map your datasets to container paths
   - **Network**: Expose port 8080
   - **Resources**: 4GB RAM, 4 CPUs

4. **Deploy**
   - Click **Save**
   - Wait for deployment

### 6. Verify Media Access

Since your media is already on a Samba share, verify the container can access it:

```bash
# After deployment, check if media is accessible
docker exec tvchannel ls -la /media/tvchannel

# Should show your media files/folders
```

Your media files should already be in the correct location via your Samba share. The container will access them directly from the dataset path.

### 7. Access Your Stream

- **HLS Stream**: `http://your-truenas-ip:8080/channel/stream.m3u8`
- **Health Check**: `http://your-truenas-ip:8000/api/healthz` (if API is running)

## Alternative: Command Line Deployment

If you prefer command-line:

```bash
# SSH into TrueNAS
ssh root@your-truenas-ip

# Navigate to app directory (replace 'blackhole' with your pool)
cd /mnt/blackhole/apps/tvchannel  # or /mnt/tank/apps/tvchannel

# Update docker-compose.truenas.yml with your paths

# Build and start
docker-compose -f docker-compose.truenas.yml up -d

# Check status
docker-compose -f docker-compose.truenas.yml ps
docker-compose -f docker-compose.truenas.yml logs -f
```

## Verify Deployment

1. **Check container status**:
   ```bash
   docker ps | grep tvchannel
   ```

2. **Check logs**:
   ```bash
   docker logs tvchannel
   ```

3. **Test stream**:
   ```bash
   curl http://localhost:8080/channel/stream.m3u8
   ```

4. **Check health** (if API is accessible):
   ```bash
   curl http://localhost:8000/api/healthz
   ```

## Common Issues

### Port Already in Use
If port 8080 is already in use, change it in `docker-compose.truenas.yml`:
```yaml
ports:
  - "8081:8080"  # Use 8081 on host instead
```

### Permission Denied
Ensure datasets have correct permissions (replace 'blackhole' with your pool):
```bash
chmod -R 755 /mnt/blackhole/apps/tvchannel
chmod -R 777 /mnt/blackhole/apps/tvchannel/hls
```

### Can't Access Stream
1. Check firewall settings in TrueNAS
2. Verify port is exposed: `netstat -tuln | grep 8080`
3. Test from container: `docker exec tvchannel curl http://localhost:8080/channel/stream.m3u8`

## Next Steps

- Configure channel settings in `/mnt/YOUR_POOL/apps/tvchannel/config/channel_settings.json`
- Add bumper assets to `/mnt/YOUR_POOL/apps/tvchannel/assets/`
- Set up backups (see TRUENAS_SCALE_DEPLOYMENT.md)
- Configure monitoring and alerts

**Note**: Replace `YOUR_POOL` with your actual pool name (e.g., `blackhole`, `tank`, etc.)

## Support

For detailed information, see:
- `TRUENAS_SAMBA_SHARE.md` - **Using existing Samba shares** (if your media is already on SMB)
- `TRUENAS_SCALE_DEPLOYMENT.md` - Full deployment guide
- `PRODUCTION_DEPLOYMENT.md` - Production best practices
- `README.md` - General documentation

