namespace MeetingBot.Models.Requests;

public sealed class CreateMeetingRequest
{
    public string OrganizerUserIdOrUpn { get; init; } = string.Empty;

    public string Subject { get; init; } = "Bot test meeting via Graph";

    public DateTimeOffset? StartDateTimeUtc { get; init; }

    public DateTimeOffset? EndDateTimeUtc { get; init; }
}
