using System.ComponentModel.DataAnnotations;

namespace MeetingBot.Models.Requests;

public sealed class StartMeetingRequest
{
    [Required]
    public string RoomId { get; init; } = string.Empty;

    [Required]
    public string MeetingJoinUrl { get; init; } = string.Empty;
}
