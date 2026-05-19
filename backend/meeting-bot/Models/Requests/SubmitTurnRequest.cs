namespace MeetingBot.Models.Requests;

public sealed class SubmitTurnRequest
{
    public string Transcript { get; init; } = string.Empty;

    public string? TurnId { get; init; }
}
