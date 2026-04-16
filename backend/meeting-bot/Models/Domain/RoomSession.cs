namespace MeetingBot.Models.Domain;

public enum RoomStatus
{
    Created,
    Joining,
    Established,
    Leaving,
    Ended,
    Failed
}

public sealed class CallEvent
{
    public DateTimeOffset TimestampUtc { get; init; } = DateTimeOffset.UtcNow;

    public string EventType { get; init; } = string.Empty;

    public string Details { get; init; } = string.Empty;
}

public sealed class RoomSession
{
    public string RoomId { get; init; } = string.Empty;

    public string MeetingJoinUrl { get; init; } = string.Empty;

    public string? CallId { get; set; }

    public RoomStatus Status { get; set; } = RoomStatus.Created;

    public DateTimeOffset StartedAtUtc { get; set; } = DateTimeOffset.UtcNow;

    public DateTimeOffset? EndedAtUtc { get; set; }

    public string? LeaveReason { get; set; }

    public List<CallEvent> Events { get; } = new();
}
