#!/bin/bash
# Verify the syntax fix is in the file on TrueNAS

echo "Checking server/stream.py for the fix..."
echo ""

cd /mnt/blackhole/apps/channel

echo "Line 141 (should have 'global _current_ffmpeg_process'):"
sed -n '141p' server/stream.py
echo ""

echo "Line 281 (should be a COMMENT, NOT 'global'):"
sed -n '281p' server/stream.py
echo ""

echo "Lines 280-282 (context around line 281):"
sed -n '280,282p' server/stream.py
echo ""

echo "Checking for 'global _current_ffmpeg_process' at line 281:"
if grep -n "^[[:space:]]*global _current_ffmpeg_process" server/stream.py | grep "^281:"; then
    echo "❌ ERROR: Line 281 still has 'global' declaration - fix not applied!"
    echo ""
    echo "The file needs to be updated. Try:"
    echo "  git fetch origin"
    echo "  git reset --hard origin/main"
    echo "  git pull"
else
    echo "✓ Line 281 does NOT have global declaration - fix appears to be applied"
fi

echo ""
echo "Checking if global is at top of stream_file function (line 141):"
if grep -n "^[[:space:]]*global _current_ffmpeg_process" server/stream.py | grep "^141:"; then
    echo "✓ Global declaration is at line 141 (top of function) - correct!"
else
    echo "❌ Global declaration NOT at line 141 - file may be outdated"
fi


