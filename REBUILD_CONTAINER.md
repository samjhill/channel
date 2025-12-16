# How to Rebuild the Container on TrueNAS

## Quick Rebuild Steps

On your TrueNAS system, run:

```bash
cd /mnt/blackhole/apps/channel

# Pull latest code (if using git)
git pull

# Stop and remove existing container
docker stop tvchannel 2>/dev/null || true
docker rm tvchannel 2>/dev/null || true

# Rebuild the image
docker build -t tvchannel:latest -f server/Dockerfile .

# Start the container
docker compose -f docker-compose.truenas.yml up -d
```

## If docker compose doesn't work, use docker run:

```bash
cd /mnt/blackhole/apps/channel

# Stop and remove existing container
docker stop tvchannel 2>/dev/null || true
docker rm tvchannel 2>/dev/null || true

# Rebuild the image
docker build -t tvchannel:latest -f server/Dockerfile .

# Start with docker run
docker run -d \
  --name tvchannel \
  -p 8080:8080 \
  -v /mnt/blackhole/media/tv:/media/tvchannel:ro \
  -v /mnt/blackhole/apps/tvchannel/assets:/app/assets \
  -v /mnt/blackhole/apps/tvchannel/config:/app/config \
  -v /mnt/blackhole/apps/tvchannel/hls:/app/hls \
  --restart unless-stopped \
  tvchannel:latest
```

## Using the Deployment Script

You can also use the deployment script which handles everything:

```bash
cd /mnt/blackhole/apps/channel
./deploy-truenas-cli.sh
```

## Verify After Rebuild

```bash
# Check container is running
docker ps | grep tvchannel

# View logs
docker logs tvchannel

# Test the stream
curl http://localhost:8080/channel/stream.m3u8
```

