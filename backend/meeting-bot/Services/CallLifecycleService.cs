using System.Text.Json;
using MeetingBot.Models.Domain;
using MeetingBot.Models.Options;
using MeetingBot.Models.Requests;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class CallLifecycleService
{
    private sealed record CallNotification(string CallId, bool IsEstablished, bool IsTerminated);

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
        var notifications = ParseCallNotifications(payload);
        if (notifications.Count == 0)
        {
            // Some Graph callback payloads omit/reshape state fields.
            // As a fallback, infer call id by matching known active call ids in the payload.
            var inferredCallId = _store
                .GetAll()
                .Select(s => s.CallId)
                .FirstOrDefault(callId =>
                    !string.IsNullOrWhiteSpace(callId) &&
                    payload.Contains(callId, StringComparison.OrdinalIgnoreCase));

            if (!string.IsNullOrWhiteSpace(inferredCallId))
            {
                notifications.Add(new CallNotification(inferredCallId, IsLikelyEstablished(payload), IsLikelyTerminated(payload)));
                _logger.LogInformation("Inferred callback callId {CallId} from payload fallback parsing.", inferredCallId);
            }
        }

        foreach (var notification in notifications.Where(n => n.IsEstablished))
        {
            var callId = notification.CallId;
            if (string.IsNullOrWhiteSpace(callId))
            {
                _logger.LogWarning("Established callback received but callId is missing.");
                continue;
            }

            var session = _store.FindByCallId(callId);
            if (session is null)
            {
                _logger.LogWarning("No session found for callback callId {CallId}", callId);
                continue;
            }

            var alreadyEstablished = session.Events.Any(e => e.EventType == "call-established");
            if (!alreadyEstablished)
            {
                session.Status = RoomStatus.Established;
                session.Events.Add(new CallEvent { EventType = "call-established", Details = "Callback state established" });
                _store.Upsert(session);
            }

            // Phase 1: play fixed greeting audio into the Teams call.
            // We use Graph call action playPrompt with the media URI returned by the AI bridge.
            var alreadyRequestedGreeting = session.Events.Any(e => e.EventType == "greeting-playprompt-requested");
            if (!alreadyRequestedGreeting)
            {
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

                if (!string.IsNullOrWhiteSpace(audioUri))
                {
                    await TryPlayGreetingWithRetryAsync(session, callId, audioUri, cancellationToken);
                }
            }

            var alreadyScheduledAutoLeave = session.Events.Any(e => e.EventType == "auto-leave-scheduled");
            if (!alreadyScheduledAutoLeave)
            {
                session.Events.Add(new CallEvent { EventType = "auto-leave-scheduled", Details = $"Delay={_options.AutoLeaveSeconds}s" });
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
        }

        foreach (var notification in notifications.Where(n => n.IsTerminated))
        {
            var callId = notification.CallId;
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

    private List<CallNotification> ParseCallNotifications(string payload)
    {
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            var items = new List<JsonElement>();

            if (root.ValueKind == JsonValueKind.Object &&
                root.TryGetProperty("value", out var valueArray) &&
                valueArray.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in valueArray.EnumerateArray())
                {
                    items.Add(item);
                }
            }
            else if (root.ValueKind == JsonValueKind.Object)
            {
                items.Add(root);
            }

            var notifications = new List<CallNotification>();
            foreach (var item in items)
            {
                var callId = GetString(item, "resourceData", "id");
                if (string.IsNullOrWhiteSpace(callId))
                {
                    var resourcePath = GetString(item, "resource");
                    if (!string.IsNullOrWhiteSpace(resourcePath))
                    {
                        var marker = "/communications/calls/";
                        var idx = resourcePath.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
                        if (idx >= 0)
                        {
                            var after = resourcePath[(idx + marker.Length)..];
                            var slash = after.IndexOf('/');
                            callId = slash >= 0 ? after[..slash] : after;
                        }
                    }
                }

                var state = GetString(item, "resourceData", "state");
                var changeType = GetString(item, "changeType");
                var isEstablished = string.Equals(state, "established", StringComparison.OrdinalIgnoreCase);
                var isTerminated =
                    string.Equals(state, "terminated", StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(changeType, "deleted", StringComparison.OrdinalIgnoreCase);

                if (!string.IsNullOrWhiteSpace(callId) && (isEstablished || isTerminated))
                {
                    notifications.Add(new CallNotification(callId, isEstablished, isTerminated));
                }
            }

            return notifications;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to parse Graph callback payload.");
            return new List<CallNotification>();
        }
    }

    private static string GetString(JsonElement root, params string[] path)
    {
        var current = root;
        foreach (var segment in path)
        {
            if (current.ValueKind != JsonValueKind.Object ||
                !current.TryGetProperty(segment, out current))
            {
                return string.Empty;
            }
        }

        return current.ValueKind == JsonValueKind.String ? current.GetString() ?? string.Empty : string.Empty;
    }

    private static bool IsLikelyEstablished(string payload) =>
        payload.Contains("\"state\":\"established\"", StringComparison.OrdinalIgnoreCase) ||
        payload.Contains("\"status\":\"established\"", StringComparison.OrdinalIgnoreCase);

    private static bool IsLikelyTerminated(string payload) =>
        payload.Contains("\"state\":\"terminated\"", StringComparison.OrdinalIgnoreCase) ||
        payload.Contains("\"status\":\"terminated\"", StringComparison.OrdinalIgnoreCase) ||
        payload.Contains("\"changeType\":\"deleted\"", StringComparison.OrdinalIgnoreCase);

    private async Task TryPlayGreetingWithRetryAsync(RoomSession session, string callId, string audioUri, CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var delay = TimeSpan.FromSeconds(2);
        Exception? lastException = null;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                await _graphCallsClient.PlayPromptAsync(callId, audioUri, cancellationToken);
                session.Events.Add(
                    new CallEvent
                    {
                        EventType = "greeting-playprompt-requested",
                        Details = $"Requested Graph playPrompt on attempt {attempt}"
                    });
                _store.Upsert(session);
                return;
            }
            catch (Exception ex) when (IsNotEstablishedPlayPromptError(ex) && attempt < maxAttempts)
            {
                lastException = ex;
                _logger.LogInformation(
                    "playPrompt attempt {Attempt}/{MaxAttempts} deferred for room {RoomId} call {CallId}: call not established yet.",
                    attempt,
                    maxAttempts,
                    session.RoomId,
                    callId);
                await Task.Delay(delay, cancellationToken);
            }
            catch (Exception ex)
            {
                lastException = ex;
                break;
            }
        }

        if (lastException is not null)
        {
            _logger.LogWarning(lastException, "playPrompt failed for room {RoomId} call {CallId}", session.RoomId, callId);
            session.Events.Add(new CallEvent { EventType = "greeting-playprompt-failed", Details = lastException.Message });
            _store.Upsert(session);
        }
    }

    private static bool IsNotEstablishedPlayPromptError(Exception ex)
    {
        if (ex is not HttpRequestException httpEx || string.IsNullOrWhiteSpace(httpEx.Message))
        {
            return false;
        }

        return httpEx.Message.Contains("\"code\":\"8501\"", StringComparison.OrdinalIgnoreCase) ||
               httpEx.Message.Contains("not in Established state", StringComparison.OrdinalIgnoreCase);
    }
}
