import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import * as api from "../api";

vi.mock("../api");

describe("App", () => {
  const mockChannels = [
    {
      id: "channel-1",
      name: "Channel 1",
      enabled: true,
      media_root: "/media/tv",
      playback_mode: "sequential" as const,
      loop_entire_library: true,
      shows: [],
    },
  ];

  const mockChannel = {
    ...mockChannels[0],
    shows: [
      {
        id: "show-1",
        label: "Show 1",
        path: "Show 1",
        include: true,
        playback_mode: "inherit" as const,
        weight: 1.0,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.fetchChannels as any).mockResolvedValue(mockChannels);
    (api.fetchChannel as any).mockResolvedValue(mockChannel);
    (api.saveChannel as any).mockResolvedValue(undefined);
  });

  it("should render and load channels", async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(api.fetchChannels).toHaveBeenCalled();
    });

    expect(screen.getByText("Channel Admin")).toBeInTheDocument();
  });

  it("should display channel selector", async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(screen.getByText("Channel 1")).toBeInTheDocument();
    });
  });

  it("should switch between settings and playlist views", async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(screen.getByText("Channel 1")).toBeInTheDocument();
    });

    // Find the button by role and text
    const playlistButton = screen.getByRole("button", { name: /playlist management/i });
    await userEvent.click(playlistButton);
    
    // Should show playlist view
    expect(playlistButton.classList.contains("active")).toBe(true);
  });

  it("should handle save action", async () => {
    render(<App />);
    
    await waitFor(() => {
      expect(api.fetchChannel).toHaveBeenCalled();
    });

    // Switch to settings view to make changes
    const settingsButton = screen.getByRole("button", { name: /channel settings/i });
    await userEvent.click(settingsButton);

    // Make a change to enable save button (change media_root)
    await waitFor(() => {
      const mediaRootInput = screen.getByLabelText(/TV Folder/i);
      expect(mediaRootInput).toBeInTheDocument();
    });

    const mediaRootInput = screen.getByLabelText(/TV Folder/i) as HTMLInputElement;
    await userEvent.clear(mediaRootInput);
    await userEvent.type(mediaRootInput, "/new/media/path");

    // Mock window.confirm to return true
    window.confirm = vi.fn(() => true);

    // Wait for save button to be enabled
    await waitFor(() => {
      const saveButton = screen.getByRole("button", { name: /save/i });
      expect(saveButton).not.toBeDisabled();
    });

    const saveButton = screen.getByRole("button", { name: /save/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(api.saveChannel).toHaveBeenCalled();
    });
  });
});

