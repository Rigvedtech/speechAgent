namespace MeetingBot.Models.Options;

public sealed class AcsOptions
{
    public const string SectionName = "Acs";

    /// <summary>ACS resource connection string (endpoint + accesskey).</summary>
    public string ConnectionString { get; init; } = string.Empty;

    /// <summary>Communication user id (8:acs:...) used as call source. Created at startup if empty.</summary>
    public string BotCommunicationUserId { get; init; } = string.Empty;

    /// <summary>Optional display name for the bot in the meeting roster.</summary>
    public string BotDisplayName { get; init; } = "Interview Bot";

    /// <summary>Call Automation REST api-version.</summary>
    public string ApiVersion { get; init; } = "2025-05-15";

    /// <summary>Relative path for Call Automation CloudEvents (appended to MeetingBot:CallbackBaseUrl).</summary>
    public string EventsCallbackPath { get; init; } = "/api/acs/events";

    /// <summary>Relative WebSocket path ACS connects to for media (wss + CallbackBaseUrl host).</summary>
    public string MediaWebSocketPath { get; init; } = "/ws/acs-media";

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(ConnectionString);
}
