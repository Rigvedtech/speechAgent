using System.Collections.Concurrent;
using MeetingBot.Models.Domain;

namespace MeetingBot.Services;

public sealed class RoomSessionStore
{
    private readonly ConcurrentDictionary<string, RoomSession> _sessions = new(StringComparer.OrdinalIgnoreCase);

    public RoomSession Upsert(RoomSession session)
    {
        _sessions.AddOrUpdate(session.RoomId, session, (_, _) => session);
        return session;
    }

    public bool TryGet(string roomId, out RoomSession? session) => _sessions.TryGetValue(roomId, out session);

    public RoomSession? FindByCallId(string callId) =>
        _sessions.Values.FirstOrDefault(s => string.Equals(s.CallId, callId, StringComparison.OrdinalIgnoreCase));

    public IReadOnlyCollection<RoomSession> GetAll() => _sessions.Values.ToArray();
}
