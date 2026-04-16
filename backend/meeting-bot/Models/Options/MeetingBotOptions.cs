namespace MeetingBot.Models.Options;

public sealed class MeetingBotOptions
{
    public const string SectionName = "MeetingBot";

    public string CallbackBaseUrl { get; init; } = string.Empty;

    public string PublicServiceHost { get; init; } = string.Empty;

    public string OrganizerUserIdOrUpn { get; init; } = string.Empty;

    public string FixedGreetingLine { get; init; } = "Hello, I am the interview bot. Audio path check passed.";

    public int AutoLeaveSeconds { get; init; } = 45;
}
