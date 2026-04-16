using MeetingBot.Models.Domain;
using MeetingBot.Models.Options;
using MeetingBot.Models.Requests;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class CallLifecycleService
{
    private readonly GraphCallsClient _graphCallsClient;
    private readonly RoomSessionStore _store;
    private readonly AiBridgeClient _aiBridgeClient;
    private readonly ILogger<CallLifecycleService> _logger;
    private readonly MeetingBotOptions _options;

    public CallLifecycleService(
        GraphCallsClient graphCallsClient,
        RoomSessionStore store,
        AiBridgeClient aiBridgeClient,
        IOptions<MeetingBotOptions> options,
        ILogger<CallLifecycleService> logger)
    {
        _graphCallsClient = graphCallsClient;
        _store = store;
        _aiBridgeClient = aiBridgeClient;
        _logger = logger;
        _options = options.Value;
    }

    public async Task<RoomSession> StartAsync(StartMeetingRequest request, CancellationToken cancellationToken)
    {
        var session = new RoomSession
        {
            RoomId = request.RoomId,
            MeetingJoinUrl = request.MeetingJoinUrl,
            Status = RoomStatus.Joining,
            StartedAtUtc = DateTimeOffset.UtcNow
        };
        session.Events.Add(new CallEvent { EventType = "start-requested", Details = "Start endpoint triggered" });
        _store.Upsert(session);

        var callId = await _graphCallsClient.CreateMeetingCallAsync(request.MeetingJoinUrl, cancellationToken);
        session.CallId = callId;
        session.Events.Add(new CallEvent { EventType = "graph-call-created", Details = $"CallId={callId}" });
        _store.Upsert(session);
        return session;
    }

    public async Task<bool> LeaveAsync(string roomId, string reason, CancellationToken cancellationToken)
    {
        if (!_store.TryGet(roomId, out var session) || session is null || string.IsNullOrWhiteSpace(session.CallId))
        {
            return false;
        }

        session.Status = RoomStatus.Leaving;
        session.Events.Add(new CallEvent { EventType = "leave-requested", Details = reason });
        _store.Upsert(session);

        await _graphCallsClient.EndCallAsync(session.CallId, cancellationToken);
        session.Status = RoomStatus.Ended;
        session.EndedAtUtc = DateTimeOffset.UtcNow;
        session.LeaveReason = reason;
        session.Events.Add(new CallEvent { EventType = "call-ended", Details = reason });
        _store.Upsert(session);
        return true;
    }

    public async Task HandleCallbackAsync(string payload, CancellationToken cancellationToken)
    {
        // Graph callback payload can include multiple notifications. Keep parser tolerant.
        var normalized = payload.ToLowerInvariant();
        var established = normalized.Contains("\"state\":\"established\"") || normalized.Contains("\"established\"");
        var terminated = normalized.Contains("\"state\":\"terminated\"") || normalized.Contains("\"terminated\"");

        if (established)
        {
            var callId = ExtractValue(payload, "\"id\":\"");
            if (string.IsNullOrWhiteSpace(callId))
            {
                _logger.LogWarning("Established callback received but callId is missing.");
                return;
            }

            var session = _store.FindByCallId(callId);
            if (session is null)
            {
                _logger.LogWarning("No session found for callback callId {CallId}", callId);
                return;
            }

            session.Status = RoomStatus.Established;
            session.Events.Add(new CallEvent { EventType = "call-established", Details = "Callback state established" });
            _store.Upsert(session);

            var audioUri = await _aiBridgeClient.RequestFixedPhraseAsync(
                session.RoomId,
                callId,
                _options.FixedGreetingLine,
                cancellationToken);
            session.Events.Add(
                new CallEvent
                {
                    EventType = "fixed-line-ready",
                    Details = audioUri is null
                        ? "No AI audio URI returned; continue with media SDK implementation."
                        : $"AI audio URI generated: {audioUri}"
                });
            _store.Upsert(session);

            _ = Task.Run(
                async () =>
                {
                    try
                    {
                        await Task.Delay(TimeSpan.FromSeconds(_options.AutoLeaveSeconds), cancellationToken);
                        await LeaveAsync(session.RoomId, "auto-leave-timer", cancellationToken);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Auto-leave timer failed for room {RoomId}", session.RoomId);
                    }
                },
                cancellationToken);
        }

        if (terminated)
        {
            var callId = ExtractValue(payload, "\"id\":\"");
            var session = string.IsNullOrWhiteSpace(callId) ? null : _store.FindByCallId(callId);
            if (session is not null)
            {
                session.Status = RoomStatus.Ended;
                session.EndedAtUtc = DateTimeOffset.UtcNow;
                session.LeaveReason ??= "terminated-callback";
                session.Events.Add(new CallEvent { EventType = "call-terminated-callback", Details = "Graph callback terminated" });
                _store.Upsert(session);
            }
        }
    }

    private static string ExtractValue(string source, string token)
    {
        var idx = source.IndexOf(token, StringComparison.OrdinalIgnoreCase);
        if (idx < 0)
        {
            return string.Empty;
        }

        var start = idx + token.Length;
        var end = source.IndexOf('"', start);
        return end > start ? source[start..end] : string.Empty;
    }
}
