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

    public int NextTurnId { get; set; } = 1;

    public bool IsProcessingTurn { get; set; }

    public string? LastUserUtterance { get; set; }

    public string? LastBotReply { get; set; }

    public DateTimeOffset? LastPlayPromptAtUtc { get; set; }

    /// <summary>While set and in the future, Windows STT loop ignores finals (reduces echo after bot speaks).</summary>
    public DateTimeOffset? SttSuppressedUntilUtc { get; set; }

    public string? LastSttForwardedText { get; set; }

    public DateTimeOffset? LastSttForwardedAtUtc { get; set; }

    public string? LastTurnTraceId { get; set; }

    public HashSet<string> ProcessedTurnKeys { get; } = new(StringComparer.OrdinalIgnoreCase);

    public List<CallEvent> Events { get; } = new();
}
