# Disjointed Logic Audit

This document identifies areas where the same concept is implemented differently across the codebase, which can lead to inconsistencies and bugs.

## 1. Entry Type Checking (CRITICAL)

**Problem**: Multiple implementations of `is_episode_entry()`, `is_weather_bumper()`, etc. with different logic.

### Locations:
- `server/playlist_service.py`:
  - `is_episode_entry()` - Uses `entry_type()` which checks file extensions
  - `is_weather_bumper()` - Uses `_normalize_token()` and checks for "weather_bumper" or "/bumpers/weather/"
  - `entry_type()` - Comprehensive type checking with normalization

- `server/stream.py`:
  - `is_bumper_block()` - Simple `entry.strip().upper() == "BUMPER_BLOCK"`
  - `is_weather_bumper()` - Simple `entry.strip() == "WEATHER_BUMPER"`
  - `is_episode_entry()` - Uses `entry_type()` from `playlist_service` (good!)

- `server/api/app.py`:
  - `skip_current_episode()` has inline `_is_episode_entry()`:
    ```python
    def _is_episode_entry(entry: str) -> bool:
        normalized = entry.strip().upper()
        if normalized in {"BUMPER_BLOCK", "WEATHER_BUMPER"}:
            return False
        return "/" in entry and not entry.startswith("#")
    ```
    This is DIFFERENT from `playlist_service.is_episode_entry()`!

### Impact:
- `skip_current_episode()` might skip to wrong entries
- Inconsistent behavior between API and streamer
- Could cause bugs when playlist format changes

### Recommendation:
- **Consolidate**: All code should use `playlist_service.is_episode_entry()` and related functions
- Remove duplicate implementations in `stream.py` and `api/app.py`
- Import from `playlist_service` everywhere

---

## 2. Finding Next Episode (CRITICAL)

**Problem**: Multiple ways to find the "next" episode, leading to inconsistencies.

### Locations:
- `server/api/app.py` - `skip_current_episode()`:
  - Searches raw entries for current episode
  - Advances index by 1
  - Skips markers with inline `_is_episode_entry()`
  - **Does NOT use segments**

- `server/api/app.py` - `build_playlist_snapshot()`:
  - Uses `build_playlist_segments()` to create segments
  - Uses `_resolve_current_segment_index()` to find current
  - Returns `upcoming_segments = segments[current_idx + 1:]`
  - **Uses segments**

- `server/api/app.py` - `_find_next_bumper_block()` (now fixed):
  - Was searching for BUMPER_BLOCK markers directly
  - Now uses segments (FIXED)

- `server/stream.py` - `run_stream()`:
  - Uses playhead state + FFmpeg process state
  - Complex logic to determine current_index
  - **Different from API**

### Impact:
- Skip button might skip to different episode than what playlist shows
- Preview might show different episode than playlist
- Streamer might play different episode than API thinks is current

### Recommendation:
- **Create unified function**: `find_next_episode(entries, current_state)` that:
  1. Uses segments (like playlist view)
  2. Returns the actual next episode segment
  3. Can be used by API, streamer, and preview
- Update `skip_current_episode()` to use segments
- Ensure streamer uses same logic (or at least validates against segments)

---

## 3. Playlist Loading (MEDIUM)

**Problem**: Two different playlist loading functions.

### Locations:
- `server/playlist_service.py` - `load_playlist_entries()`:
  - Has mtime-based caching
  - Returns `(entries, mtime)` tuple
  - Used by API

- `server/stream.py` - `load_playlist()`:
  - No caching
  - Returns `(files, mtime)` tuple
  - Used by streamer

### Impact:
- Streamer doesn't benefit from caching
- Potential for inconsistent mtime values
- Code duplication

### Recommendation:
- **Consolidate**: Streamer should use `playlist_service.load_playlist_entries()`
- Remove `load_playlist()` from `stream.py`
- Update all references

---

## 4. Current Episode Resolution (MEDIUM)

**Problem**: Different ways to determine what's "currently playing".

### Locations:
- `server/api/app.py` - `_resolve_current_segment_index()`:
  - Uses segments
  - Finds segment containing `current_path` from playhead
  - Returns segment index

- `server/stream.py` - `run_stream()`:
  - Checks FFmpeg process state (priority 1)
  - Falls back to playhead state (priority 2)
  - Complex logic with multiple fallbacks
  - Returns raw entry index

### Impact:
- API and streamer might disagree on what's current
- Could cause skip detection issues
- Preview might show wrong episode

### Recommendation:
- **Create unified function**: `resolve_current_episode(entries, playhead_state, ffmpeg_state=None)`
- Returns both segment index and raw entry index
- Can be used by both API and streamer
- Streamer can still prioritize FFmpeg state, but validate against segments

---

## 5. Weather Bumper Detection (LOW)

**Problem**: Different ways to check if weather bumper should be included.

### Locations:
- `server/stream.py` - `_should_include_weather()`:
  - Uses deterministic seed based on episode path
  - Checks weather config and probability
  - **Unified function** (good!)

- `server/api/app.py` - `_find_next_bumper_block()`:
  - Has inline weather check logic
  - Uses same deterministic seed approach
  - **Duplicated logic**

### Impact:
- Code duplication
- If logic changes, need to update multiple places

### Recommendation:
- **Already unified**: `_should_include_weather()` exists
- Update `_find_next_bumper_block()` to use `_should_include_weather()`
- Remove duplicate weather check logic

---

## Summary

### Critical Issues:
1. ✅ **FIXED** - **Entry type checking** - Consolidated to use `playlist_service` functions everywhere
2. ✅ **FIXED** - **Finding next episode** - `skip_current_episode()` now uses segments (like playlist view)
3. ✅ **FIXED** - **Current episode resolution** - Added unified `resolve_current_episode()` and `find_next_episode()` functions

### Medium Issues:
4. ✅ **FIXED** - **Playlist loading** - Streamer now uses `playlist_service.load_playlist_entries()` (with caching)
5. ✅ **FIXED** - **Weather bumper detection** - `_find_next_bumper_block()` now uses `_should_include_weather()`

### Changes Made:
1. ✅ Consolidated entry type checking - Removed duplicates in `stream.py` and `api/app.py`, all use `playlist_service` functions
2. ✅ Updated `skip_current_episode()` - Now uses `build_playlist_segments()` and `find_segment_index_for_entry()` for consistency
3. ✅ Consolidated playlist loading - `stream.py` now uses `load_playlist_entries()` via alias `load_playlist = load_playlist_entries`
4. ✅ Updated weather checks - `_find_next_bumper_block()` now uses `_should_include_weather()` from `stream.py`
5. ✅ Added unified functions - `resolve_current_episode()` and `find_next_episode()` in `playlist_service.py` for future use

