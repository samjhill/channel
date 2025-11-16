# Project Issues Report

Generated: 2025-11-16

## 🔴 Critical Issues

### 1. Missing File Validation Before Streaming ✅ **FIXED**
**Location**: `server/stream.py:182-250`
**Status**: ✅ Fixed - Added file existence and file type validation before streaming
**Changes**: 
- Added `os.path.exists()` and `os.path.isfile()` checks
- Function now returns `bool` to indicate success/failure
- Error messages logged when files are missing

### 2. FFmpeg Errors Silently Ignored ✅ **FIXED**
**Location**: `server/stream.py:243-248`
**Status**: ✅ Fixed - Now checks FFmpeg return code and handles errors
**Changes**:
- Captures subprocess result
- Checks `returncode != 0` and logs error
- Returns `False` on failure, `True` on success

### 3. Watch Progress Marked Even If Streaming Fails ✅ **FIXED**
**Location**: `server/stream.py:296-304`
**Status**: ✅ Fixed - Only marks episodes as watched if streaming succeeded
**Changes**:
- Checks `streaming_succeeded` return value
- Only calls `mark_episode_watched()` if streaming completed successfully
- Logs warning when skipping watch progress for failed streams

### 4. No Error Handling for Missing Video Files in Playlist ✅ **FIXED**
**Location**: `server/stream.py:281-294`
**Status**: ✅ Fixed - Validates all playlist entries before processing
**Changes**:
- Filters playlist to only include valid, existing files
- Logs warnings for invalid entries
- Skips invalid files instead of attempting to stream them

## 🟡 Medium Priority Issues

### 5. Watch Progress File Could Grow Indefinitely
**Location**: `server/playlist_service.py:398-410`
**Issue**: Every watched episode is stored permanently. Over time, this file could grow very large with thousands of entries.
**Impact**: Performance degradation, disk space usage
**Fix**: Implement cleanup of old entries or limit to last N episodes

### 6. No Validation of Watch Progress Entries
**Location**: `server/generate_playlist.py:635-645`
**Issue**: When resuming from last watched episode, there's no check that the episode path still exists or is valid.
**Impact**: Could try to resume from a deleted/moved episode
**Fix**: Validate episode exists before using it for resume

### 7. Race Condition in Watch Progress Updates
**Location**: `server/playlist_service.py:398-410`
**Issue**: `mark_episode_watched()` loads, modifies, and saves the progress file. If multiple processes call this simultaneously, updates could be lost.
**Impact**: Watch progress could be inconsistent
**Fix**: Use file locking or atomic writes (already using tempfile + replace, but no locking)

### 8. Entrypoint Doesn't Handle Process Failures
**Location**: `server/entrypoint.sh:8-12`
**Issue**: Background processes (`&`) are started but there's no monitoring or restart logic if they crash.
**Impact**: If generate_playlist.py or stream.py crashes, the container keeps running but nothing works
**Fix**: Add process monitoring or use a proper process manager

### 9. Video Height Cache Never Cleared
**Location**: `server/stream.py:77,108-141`
**Issue**: `_video_height_cache` is a global dict that grows indefinitely. If files are deleted, cache entries remain.
**Impact**: Memory leak over time
**Fix**: Implement cache size limit or periodic cleanup

### 10. No Timeout on FFprobe Calls
**Location**: `server/stream.py:117-133`
**Issue**: `ffprobe` calls have no timeout. If a file is corrupted or on a slow network mount, it could hang indefinitely.
**Impact**: Stream could hang when trying to probe problematic files
**Fix**: Add timeout to subprocess.run()

## 🟢 Low Priority / Code Quality Issues

### 11. Missing Error Handling in Bumper Generation
**Location**: `server/generate_playlist.py:443-455`
**Issue**: Network bumper generation catches all exceptions but doesn't log detailed error information.
**Impact**: Hard to debug bumper generation failures

### 12. No Cleanup of Old HLS Segments
**Location**: `server/stream.py:226-227`
**Issue**: HLS segments are created with `delete_segments` flag, but if the stream crashes, old segments might accumulate.
**Impact**: Disk space usage over time

### 13. Playlist Regeneration Doesn't Validate Episode Paths
**Location**: `server/generate_playlist.py:511-527`
**Issue**: Episodes are collected but not validated as readable video files before being added to playlist.
**Impact**: Playlist could contain unreadable files

### 14. No Logging of Watch Progress Operations
**Location**: `server/playlist_service.py:398-410`
**Issue**: Watch progress updates happen silently. No logging for debugging.
**Impact**: Hard to debug watch progress issues

### 15. Resume Logic Could Skip Episodes
**Location**: `server/generate_playlist.py:635-648`
**Issue**: If the last watched episode appears multiple times in the playlist (unlikely but possible), it only finds the first occurrence.
**Impact**: Could resume from wrong position

### 16. No Handling of Special Characters in File Paths
**Location**: Throughout codebase
**Issue**: File paths with special characters, spaces, or unicode might cause issues in subprocess calls.
**Impact**: Some video files might not stream correctly

### 17. Missing Type Hints in Some Functions
**Location**: `server/stream.py:182`, `server/generate_playlist.py:674`
**Issue**: Some functions lack return type hints.
**Impact**: Reduced code clarity and IDE support

### 18. No Configuration Validation
**Location**: `server/config/channel_settings.json`
**Issue**: No schema validation for config files. Invalid configs could cause runtime errors.
**Impact**: Hard to debug configuration issues

## 📋 Summary

**Critical Issues**: 4
**Medium Priority**: 6  
**Low Priority**: 8

**Total Issues Found**: 18

## 🔧 Recommended Fix Priority

1. **Immediate**: Fix issues #1, #2, #3 (streaming error handling)
2. **Short-term**: Fix issues #5, #6, #7 (watch progress improvements)
3. **Medium-term**: Fix issues #8, #9, #10 (process management and resource cleanup)
4. **Long-term**: Address code quality issues (#11-18)

