namespace MeetingBot.Models.Options;

public sealed class MeetingBotOptions
{
    public const string SectionName = "MeetingBot";

    public string CallbackBaseUrl { get; init; } = string.Empty;

    public string PublicServiceHost { get; init; } = string.Empty;

    public string OrganizerUserIdOrUpn { get; init; } = string.Empty;

    public string FixedGreetingLine { get; init; } = "Hello, I am the interview bot. Audio path check passed.";

    /// <summary>When &gt; 0, the bot ends the call automatically after this many seconds post-establish. 0 disables auto-leave.</summary>
    public int AutoLeaveSeconds { get; init; }

    // Phase-3/Media: when true, join uses Graph Communications SDK + app-hosted media (see MediaPlatform).
    public bool UseApplicationHostedMedia { get; init; }

    /// <summary>Graph base URL for Communications SDK outbound calls (v1.0).</summary>
    public string PlaceCallEndpointUrl { get; init; } = "https://graph.microsoft.com/v1.0";

    // Websocket URL for STT streaming service (e.g. ws://127.0.0.1:8020/stt).
    public string SttWebSocketUrl { get; init; } = "ws://127.0.0.1:8020/stt";

    /// <summary>
    /// When true (Windows only), after the greeting the bot captures local PC audio (see SttLocalAudioSource),
    /// streams PCM to the STT websocket, and on each final transcript calls the same path as /api/rooms/{id}/turn.
    /// This is a practical Step A for dev: run Teams on the same machine as the bot and use Loopback to hear the meeting
    /// through the speakers. True in-call RTP capture requires application-hosted Graph media (separate milestone).
    /// </summary>
    public bool EnableSttVoiceLoop { get; init; }

    /// <summary>None | Mic | Loopback. Loopback = default render device (what you hear from Teams).</summary>
    public string SttLocalAudioSource { get; init; } = "Loopback";

    /// <summary>Ignore STT finals for this long after playPrompt to reduce self-echo from speakers.</summary>
    public int SttSuppressionAfterPlaySeconds { get; init; } = 12;

    /// <summary>Ignore very short STT finals (noise).</summary>
    public int SttMinTranscriptLength { get; init; } = 4;

    /// <summary>Ignore STT finals with fewer than this many words (reduces single-token hallucinations while muted).</summary>
    public int SttMinWordCount { get; init; } = 2;
}
