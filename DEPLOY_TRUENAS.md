# Deploy to TrueNAS Scale - Step by Step

## Prerequisites Completed ✅

- ✅ Pool identified: `blackhole`
- ✅ Datasets created: `/mnt/blackhole/apps/tvchannel/*`
- ✅ Media path configured: `/mnt/blackhole/media/tv`
- ✅ Docker Compose file ready

## Deployment Options

### Option 1: Deploy via TrueNAS Apps UI (Recommended)

1. **Access TrueNAS Web Interface**
   - Navigate to `http://your-truenas-ip`
   - Log in

2. **Install Custom App**
   - Go to **Apps** → **Discover Apps**
   - Click **⋮** (three dots menu) → **Install via YAML**

3. **Configure the App**
   - **Application Name**: `tvchannel`
   - **Custom Config**: Copy the entire contents of `docker-compose.truenas.yml`
   - **Image Repository**: Leave blank (we're using docker-compose build)

4. **Configure Storage** (if prompted)
   - Map volumes:
     - `/mnt/blackhole/media/tv` → `/media/tvchannel` (read-only)
     - `/mnt/blackhole/apps/tvchannel/assets` → `/app/assets`
     - `/mnt/blackhole/apps/tvchannel/config` → `/app/config`
     - `/mnt/blackhole/apps/tvchannel/hls` → `/app/hls`

5. **Configure Networking**
   - **Port**: `8080` (for HLS stream)
   - **Type**: `NodePort` or `LoadBalancer`

6. **Configure Resources** (if prompted)
   - **CPU**: 4 cores
   - **Memory**: 4GB

7. **Deploy**
   - Click **Save**
   - Wait for deployment (may take a few minutes to build)

### Option 2: Deploy via Command Line

```bash
# SSH into TrueNAS
ssh root@your-truenas-ip

# Navigate to app directory
cd /mnt/blackhole/apps/tvchannel

# Pull latest code (if needed)
git pull

# Build and start
docker-compose -f docker-compose.truenas.yml up -d --build

# Check status
docker-compose -f docker-compose.truenas.yml ps

# View logs
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

4. **Check health**:
   ```bash
   curl http://localhost:8000/api/healthz
   ```

## Access Your Stream

- **HLS Stream**: `http://your-truenas-ip:8080/channel/stream.m3u8`
- **Health Check**: `http://your-truenas-ip:8000/api/healthz`

## Troubleshooting

### Container won't start
- Check logs: `docker logs tvchannel`
- Verify paths exist: `ls -la /mnt/blackhole/apps/tvchannel/`
- Check permissions: `ls -ld /mnt/blackhole/apps/tvchannel/*`

### Can't access stream
- Check firewall: Ensure port 8080 is open
- Verify port mapping: `docker port tvchannel`
- Test from container: `docker exec tvchannel curl http://localhost:8080/channel/stream.m3u8`

### Media not found
- Verify media path: `ls -la /mnt/blackhole/media/tv`
- Check mount: `docker exec tvchannel ls -la /media/tvchannel`
- If your Samba share is at a different path, update docker-compose.truenas.yml

## Next Steps After Deployment

1. **Configure channel settings**:
   ```bash
   nano /mnt/blackhole/apps/tvchannel/config/channel_settings.json
   ```

2. **Add bumper assets** (optional):
   - Place assets in `/mnt/blackhole/apps/tvchannel/assets/`

3. **Monitor logs**:
   ```bash
   docker logs -f tvchannel
   ```

4. **Check playlist generation**:
   - The app will automatically generate playlists
   - Check logs for progress

