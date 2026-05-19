namespace MeetingBot.Services;

/// <summary>
/// Starts/stops the optional local-audio → STT → auto-turn loop (Step A dev path on Windows).
/// </summary>
public interface ISttVoiceLoopStarter
{
    /// <summary>Begin capturing audio for this room after the greeting (no-op if disabled / non-Windows).</summary>
    void RequestStartAfterGreeting(string roomId);

    /// <summary>Stop capture and STT for this room (e.g. leave or call terminated).</summary>
    Task StopAsync(string roomId, CancellationToken cancellationToken = default);
}
