using System.ComponentModel.DataAnnotations;

namespace MeetingBot.Models.Requests;

public sealed class LeaveMeetingRequest
{
    [Required]
    public string RoomId { get; init; } = string.Empty;

    public string Reason { get; init; } = "manual-stop";
}
