#!/bin/bash
# More detailed diagnostic for admin UI

echo "========================================="
echo "Detailed Admin UI Check"
echo "========================================="
echo ""

# Check dist folder contents
echo "1. Dist folder contents:"
docker exec tvchannel find /app/ui/channel-admin/dist -type f | head -20
echo ""

# Check index.html content
echo "2. First 20 lines of index.html:"
docker exec tvchannel head -20 /app/ui/channel-admin/dist/index.html
echo ""

# Test from inside container
echo "3. Testing HTTP response from inside container:"
docker exec tvchannel curl -s http://localhost:8080/ | head -20
echo ""

# Check port mapping
echo "4. Container port mapping:"
docker port tvchannel
echo ""

# Test from host (if possible)
echo "5. Testing from host (if accessible):"
curl -I http://192.168.2.39:8080/ 2>&1 | head -10
echo ""

# Check nginx access logs
echo "6. Recent nginx access logs:"
docker exec tvchannel tail -10 /var/log/nginx/access.log 2>&1 | tail -5
echo ""

# Check if assets folder has files
echo "7. Assets folder contents:"
docker exec tvchannel ls -la /app/ui/channel-admin/dist/assets/ 2>&1 | head -10
echo ""

echo "========================================="
echo "If index.html is very small (<1KB), the build may have failed."
echo "Check Docker build logs for npm errors."

