#!/bin/bash
# Test UI and API connectivity

echo "========================================="
echo "UI and API Connectivity Test"
echo "========================================="
echo ""

# Test API from inside container
echo "1. Testing API from inside container:"
docker exec tvchannel curl -s http://localhost:8000/api/healthz | python3 -m json.tool 2>/dev/null || docker exec tvchannel curl -s http://localhost:8000/api/healthz
echo ""

# Test API through nginx proxy
echo "2. Testing API through nginx proxy (/api/):"
docker exec tvchannel curl -s http://localhost:8080/api/healthz | python3 -m json.tool 2>/dev/null || docker exec tvchannel curl -s http://localhost:8080/api/healthz
echo ""

# Test API from host
echo "3. Testing API from host:"
curl -s http://192.168.2.39:8080/api/healthz | python3 -m json.tool 2>/dev/null || curl -s http://192.168.2.39:8080/api/healthz
echo ""

# Test channels endpoint
echo "4. Testing channels endpoint:"
curl -s http://192.168.2.39:8080/api/channels | python3 -m json.tool 2>/dev/null || curl -s http://192.168.2.39:8080/api/channels
echo ""

# Check if API process is running
echo "5. Checking if API process is running:"
docker exec tvchannel ps aux | grep -E "(uvicorn|api)" | grep -v grep
echo ""

# Check process monitor logs
echo "6. Recent process monitor logs (API related):"
docker logs tvchannel 2>&1 | grep -i "api\|uvicorn" | tail -10
echo ""

# Test JavaScript file is accessible
echo "7. Testing JavaScript file accessibility:"
curl -I http://192.168.2.39:8080/assets/index-Y5ikBVvk.js 2>&1 | head -5
echo ""

# Check browser console simulation
echo "8. Simulating browser fetch to /api/channels:"
curl -v http://192.168.2.39:8080/api/channels 2>&1 | grep -E "(HTTP|Access-Control|Content-Type)" | head -10
echo ""

echo "========================================="
echo "If API calls fail, check:"
echo "1. Is the API process running? (step 5)"
echo "2. Are there errors in logs? (step 6)"
echo "3. Open browser console (F12) and check for JavaScript errors"
echo "4. Try accessing: http://192.168.2.39:8080/api/channels directly"

