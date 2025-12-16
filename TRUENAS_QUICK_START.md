# TrueNAS Scale Quick Start Guide

## Prerequisites

- TrueNAS Scale running
- SSH access (or shell access via TrueNAS UI)
- Media files ready to deploy

## Quick Deployment Steps

### 1. Prepare Storage (One-time setup)

**Option A: Using the setup script** (recommended)
```bash
# SSH into TrueNAS Scale
ssh root@your-truenas-ip

# Clone repository
cd /mnt/tank/apps
git clone https://github.com/your-username/channel.git tvchannel
cd tvchannel

# Run setup script
chmod +x truenas-setup.sh
./truenas-setup.sh
```

**Option B: Manual setup**
```bash
# Create datasets
zfs create -p tank/apps/tvchannel/assets
zfs create -p tank/apps/tvchannel/config
zfs create -p tank/apps/tvchannel/hls

# Set permissions
chmod -R 755 /mnt/tank/apps/tvchannel
chmod -R 777 /mnt/tank/apps/tvchannel/hls
```

### 2. Update Configuration

Edit `docker-compose.truenas.yml`:

1. **Update media path** (line 15):
   ```yaml
   - /mnt/YOUR_POOL/media/tv:/media/tvchannel:ro
   ```
   Replace `YOUR_POOL` with your pool name (e.g., `tank`)

2. **Update application paths** (lines 17-19):
   ```yaml
   - /mnt/YOUR_POOL/apps/tvchannel/assets:/app/assets
   - /mnt/YOUR_POOL/apps/tvchannel/config:/app/config
   - /mnt/YOUR_POOL/apps/tvchannel/hls:/app/hls
   ```

3. **Update CORS origins** (line 23):
   ```yaml
   - CORS_ORIGINS=http://YOUR_TRUENAS_IP:5174,http://localhost:5174
   ```
   Replace `YOUR_TRUENAS_IP` with your TrueNAS IP address

### 3. Deploy via TrueNAS Apps

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

### 4. Add Media Files

Place your video files in the media dataset:
```bash
# Example structure
/mnt/tank/media/tv/
├── Show Name/
│   ├── Season 01/
│   │   └── Episode 01.mp4
│   └── Season 02/
│       └── Episode 01.mp4
```

### 5. Access Your Stream

- **HLS Stream**: `http://your-truenas-ip:8080/channel/stream.m3u8`
- **Health Check**: `http://your-truenas-ip:8000/api/healthz` (if API is running)

## Alternative: Command Line Deployment

If you prefer command-line:

```bash
# SSH into TrueNAS
ssh root@your-truenas-ip

# Navigate to app directory
cd /mnt/tank/apps/tvchannel

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
Ensure datasets have correct permissions:
```bash
chmod -R 755 /mnt/tank/apps/tvchannel
chmod -R 777 /mnt/tank/apps/tvchannel/hls
```

### Can't Access Stream
1. Check firewall settings in TrueNAS
2. Verify port is exposed: `netstat -tuln | grep 8080`
3. Test from container: `docker exec tvchannel curl http://localhost:8080/channel/stream.m3u8`

## Next Steps

- Configure channel settings in `/mnt/tank/apps/tvchannel/config/channel_settings.json`
- Add bumper assets to `/mnt/tank/apps/tvchannel/assets/`
- Set up backups (see TRUENAS_SCALE_DEPLOYMENT.md)
- Configure monitoring and alerts

## Support

For detailed information, see:
- `TRUENAS_SCALE_DEPLOYMENT.md` - Full deployment guide
- `PRODUCTION_DEPLOYMENT.md` - Production best practices
- `README.md` - General documentation

