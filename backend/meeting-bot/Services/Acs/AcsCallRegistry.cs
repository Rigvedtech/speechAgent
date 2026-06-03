using System.Collections.Concurrent;

namespace MeetingBot.Services.Acs;

/// <summary>Maps ACS callConnectionId ↔ roomId for callbacks and media WebSocket routing.</summary>
public sealed class AcsCallRegistry
{
    private readonly ConcurrentDictionary<string, string> _callToRoom = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _roomToCall = new(StringComparer.OrdinalIgnoreCase);

    public void Register(string roomId, string callConnectionId)
    {
        _roomToCall[roomId] = callConnectionId;
        _callToRoom[callConnectionId] = roomId;
    }

    public bool TryGetRoomId(string callConnectionId, out string? roomId) =>
        _callToRoom.TryGetValue(callConnectionId, out roomId);

    public bool TryGetCallConnectionId(string roomId, out string? callConnectionId) =>
        _roomToCall.TryGetValue(roomId, out callConnectionId);

    public void RemoveByRoom(string roomId)
    {
        if (_roomToCall.TryRemove(roomId, out var callId))
        {
            _callToRoom.TryRemove(callId, out _);
        }
    }

    public void RemoveByCall(string callConnectionId)
    {
        if (_callToRoom.TryRemove(callConnectionId, out var roomId))
        {
            _roomToCall.TryRemove(roomId, out _);
        }
    }
}
