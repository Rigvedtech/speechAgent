namespace MeetingBot.Models.Options;

public sealed class AiBridgeOptions
{
    public const string SectionName = "AiBridge";

    public bool Enabled { get; init; }

    public string BaseUrl { get; init; } = "http://127.0.0.1:8010";

    public int TimeoutSeconds { get; init; } = 20;
}
