import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchChannels, fetchChannel, saveChannel, discoverShows, fetchPlaylistSnapshot, updateUpcomingPlaylist, skipCurrentEpisode, } from "../api";
describe("API functions", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        globalThis.fetch = vi.fn();
    });
    describe("fetchChannels", () => {
        it("should fetch and return channels", async () => {
            const mockChannels = [
                {
                    id: "channel-1",
                    name: "Channel 1",
                    enabled: true,
                    media_root: "/media/tv",
                    playback_mode: "sequential",
                    loop_entire_library: true,
                    shows: [],
                },
            ];
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockChannels,
            });
            const result = await fetchChannels();
            expect(result).toEqual(mockChannels);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels");
        });
        it("should throw error on failed request", async () => {
            globalThis.fetch.mockResolvedValueOnce({
                ok: false,
                statusText: "Not Found",
                json: async () => ({ detail: "Channels not found" }),
            });
            await expect(fetchChannels()).rejects.toThrow("Channels not found");
        });
    });
    describe("fetchChannel", () => {
        it("should fetch a specific channel", async () => {
            const mockChannel = {
                id: "channel-1",
                name: "Channel 1",
                enabled: true,
                media_root: "/media/tv",
                playback_mode: "sequential",
                loop_entire_library: true,
                shows: [],
            };
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockChannel,
            });
            const result = await fetchChannel("channel-1");
            expect(result).toEqual(mockChannel);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1");
        });
    });
    describe("saveChannel", () => {
        it("should save a channel", async () => {
            const channel = {
                id: "channel-1",
                name: "Channel 1",
                enabled: true,
                media_root: "/media/tv",
                playback_mode: "sequential",
                loop_entire_library: true,
                shows: [],
            };
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({}),
            });
            await saveChannel(channel);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(channel),
            });
        });
    });
    describe("discoverShows", () => {
        it("should discover shows in media root", async () => {
            const mockShows = [
                {
                    id: "show-1",
                    label: "Show 1",
                    path: "Show 1",
                    include: true,
                    playback_mode: "inherit",
                    weight: 1.0,
                },
            ];
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockShows,
            });
            const result = await discoverShows("channel-1", "/media/tv");
            expect(result).toEqual(mockShows);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1/shows/discover?media_root=%2Fmedia%2Ftv");
        });
    });
    describe("fetchPlaylistSnapshot", () => {
        it("should fetch playlist snapshot", async () => {
            const mockSnapshot = {
                channel_id: "channel-1",
                version: 1234567890.0,
                fetched_at: 1234567890.0,
                current: null,
                upcoming: [],
                total_entries: 0,
                total_segments: 0,
                controllable_remaining: 0,
                limit: 25,
            };
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockSnapshot,
            });
            const result = await fetchPlaylistSnapshot("channel-1", 25);
            expect(result).toEqual(mockSnapshot);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1/playlist/next?limit=25");
        });
    });
    describe("updateUpcomingPlaylist", () => {
        it("should update playlist", async () => {
            const mockSnapshot = {
                channel_id: "channel-1",
                version: 1234567891.0,
                fetched_at: 1234567891.0,
                current: null,
                upcoming: [],
                total_entries: 0,
                total_segments: 0,
                controllable_remaining: 0,
                limit: 25,
            };
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockSnapshot,
            });
            const payload = {
                version: 1234567890.0,
                desired: ["/path/to/episode1.mp4"],
                skipped: [],
            };
            const result = await updateUpcomingPlaylist("channel-1", payload, 25);
            expect(result).toEqual(mockSnapshot);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1/playlist/next?limit=25", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
        });
    });
    describe("skipCurrentEpisode", () => {
        it("should skip current episode", async () => {
            const mockSnapshot = {
                channel_id: "channel-1",
                version: 1234567890.0,
                fetched_at: 1234567890.0,
                current: null,
                upcoming: [],
                total_entries: 0,
                total_segments: 0,
                controllable_remaining: 0,
                limit: 25,
            };
            globalThis.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockSnapshot,
            });
            const result = await skipCurrentEpisode("channel-1");
            expect(result).toEqual(mockSnapshot);
            expect(globalThis.fetch).toHaveBeenCalledWith("/api/channels/channel-1/playlist/skip-current", {
                method: "POST",
            });
        });
    });
});
