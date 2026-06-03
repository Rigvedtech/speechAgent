using System.Text.Json;
using MeetingBot.Models.Domain;
namespace MeetingBot.Services.Acs;

/// <summary>Processes ACS Call Automation CloudEvents posted to /api/acs/events.</summary>
public sealed class AcsEventHandler
{
    private readonly AcsCallRegistry _registry;
    private readonly RoomSessionStore _store;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<AcsEventHandler> _logger;

    public AcsEventHandler(
        AcsCallRegistry registry,
        RoomSessionStore store,
        IServiceScopeFactory scopeFactory,
        ILogger<AcsEventHandler> logger)
    {
        _registry = registry;
        _store = store;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public async Task HandlePayloadAsync(string payload, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            return;
        }

        foreach (var evt in ParseEvents(payload))
        {
            var eventType = evt.EventType;
            var callConnectionId = evt.CallConnectionId;
            if (string.IsNullOrWhiteSpace(callConnectionId))
            {
                continue;
            }

            _logger.LogInformation(
                "ACS event {EventType} call={CallId} context={Context}",
                eventType,
                callConnectionId,
                evt.OperationContext);

            var session = _store.FindByCallId(callConnectionId)
                ?? (!string.IsNullOrWhiteSpace(evt.OperationContext) ? ResolveByRoom(evt.OperationContext) : null);

            if (session is null && !string.IsNullOrWhiteSpace(evt.OperationContext))
            {
                session = ResolveByRoom(evt.OperationContext);
                if (session is not null)
                {
                    session.CallId = callConnectionId;
                    _registry.Register(session.RoomId, callConnectionId);
                    _store.Upsert(session);
                }
            }

            if (session is null)
            {
                _logger.LogWarning("No room session for ACS event {EventType} call={CallId}", eventType, callConnectionId);
                continue;
            }

            if (IsConnected(eventType))
            {
                session.Status = RoomStatus.Established;
                session.Events.Add(new CallEvent { EventType = "acs-call-connected", Details = eventType });
                _store.Upsert(session);

                await using var scope = _scopeFactory.CreateAsyncScope();
                var lifecycle = scope.ServiceProvider.GetRequiredService<CallLifecycleService>();
                await lifecycle.RunAcsEstablishedFlowAsync(session.RoomId, callConnectionId, cancellationToken)
                    .ConfigureAwait(false);
            }
            else if (IsDisconnected(eventType))
            {
                session.Status = RoomStatus.Ended;
                session.EndedAtUtc = DateTimeOffset.UtcNow;
                session.LeaveReason ??= eventType;
                session.Events.Add(new CallEvent { EventType = "acs-call-disconnected", Details = eventType });
                _store.Upsert(session);
                _registry.RemoveByCall(callConnectionId);
            }
            else if (IsPlayCompleted(eventType))
            {
                session.Events.Add(new CallEvent { EventType = "acs-play-completed", Details = eventType });
                _store.Upsert(session);
            }
        }
    }

    private RoomSession? ResolveByRoom(string roomId) =>
        _store.TryGet(roomId, out var s) ? s : null;

    private static bool IsConnected(string eventType) =>
        eventType.Contains("CallConnected", StringComparison.OrdinalIgnoreCase);

    private static bool IsDisconnected(string eventType) =>
        eventType.Contains("CallDisconnected", StringComparison.OrdinalIgnoreCase);

    private static bool IsPlayCompleted(string eventType) =>
        eventType.Contains("PlayCompleted", StringComparison.OrdinalIgnoreCase);

    private static IEnumerable<AcsCloudEvent> ParseEvents(string payload)
    {
        using var doc = JsonDocument.Parse(payload);
        var root = doc.RootElement;

        if (root.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in root.EnumerateArray())
            {
                var parsed = TryParseEvent(item);
                if (parsed is not null)
                {
                    yield return parsed;
                }
            }

            yield break;
        }

        if (root.ValueKind == JsonValueKind.Object)
        {
            if (root.TryGetProperty("value", out var value) && value.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in value.EnumerateArray())
                {
                    var parsed = TryParseEvent(item);
                    if (parsed is not null)
                    {
                        yield return parsed;
                    }
                }

                yield break;
            }

            var single = TryParseEvent(root);
            if (single is not null)
            {
                yield return single;
            }
        }
    }

    private static AcsCloudEvent? TryParseEvent(JsonElement item)
    {
        var eventType = item.TryGetProperty("type", out var typeEl)
            ? typeEl.GetString() ?? string.Empty
            : item.TryGetProperty("eventType", out var etEl)
                ? etEl.GetString() ?? string.Empty
                : string.Empty;

        if (string.IsNullOrWhiteSpace(eventType))
        {
            return null;
        }

        var data = item.TryGetProperty("data", out var dataEl) ? dataEl : item;
        var callConnectionId = GetString(data, "callConnectionId");
        var operationContext = GetString(data, "operationContext");

        return new AcsCloudEvent(eventType, callConnectionId, operationContext);
    }

    private static string GetString(JsonElement root, string property)
    {
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty(property, out var el))
        {
            return string.Empty;
        }

        return el.ValueKind == JsonValueKind.String ? el.GetString() ?? string.Empty : el.ToString();
    }

    private sealed record AcsCloudEvent(string EventType, string CallConnectionId, string OperationContext);
}
