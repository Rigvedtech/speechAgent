using System.Net;
using System.Text.Json;
using MeetingBot.Models.Domain;
using MeetingBot.Models.Options;
using MeetingBot.Models.Requests;
using MeetingBot.Services.Acs;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class CallLifecycleService
{
    private sealed record CallNotification(string CallId, bool IsEstablished, bool IsTerminated);

    public sealed record TurnProcessingResult(bool Success, string Message, string? TurnId = null, string? TraceId = null);

    private readonly GraphCallsClient _graphCallsClient;
    private readonly AcsCallJoinService _acsJoin;
    private readonly AcsCallActionsService _acsActions;
    private readonly AcsCallRegistry _acsRegistry;
    private readonly RoomSessionStore _store;
    private readonly AiBridgeClient _aiBridgeClient;
    private readonly ILogger<CallLifecycleService> _logger;
    private readonly MeetingBotOptions _options;

    public CallLifecycleService(
        GraphCallsClient graphCallsClient,
        AcsCallJoinService acsJoin,
        AcsCallActionsService acsActions,
        AcsCallRegistry acsRegistry,
        RoomSessionStore store,
        AiBridgeClient aiBridgeClient,
        IOptions<MeetingBotOptions> options,
        ILogger<CallLifecycleService> logger)
    {
        _graphCallsClient = graphCallsClient;
        _acsJoin = acsJoin;
        _acsActions = acsActions;
        _acsRegistry = acsRegistry;
        _store = store;
        _aiBridgeClient = aiBridgeClient;
        _logger = logger;
        _options = options.Value;
    }

    private static bool IsAcsBackend(RoomSession session) =>
        session.JoinBackend.Equals("Acs", StringComparison.OrdinalIgnoreCase);

    public async Task HandleFinalTranscriptAsync(string roomId, string transcript, CancellationToken cancellationToken)
    {
        await SubmitTurnAsync(roomId, new SubmitTurnRequest { Transcript = transcript }, cancellationToken);
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
        session.JoinBackend = _options.UseGraphJoin ? "Graph" : "Acs";
        session.Events.Add(new CallEvent { EventType = "start-requested", Details = $"{session.JoinBackend} join requested" });
        _store.Upsert(session);

        string callId;
        if (_options.UseGraphJoin)
        {
            callId = await _graphCallsClient.CreateMeetingCallAsync(request.MeetingJoinUrl, cancellationToken)
                .ConfigureAwait(false);
            session.Events.Add(new CallEvent { EventType = "graph-call-created", Details = $"CallId={callId}" });
        }
        else
        {
            if (!_acsJoin.IsConfigured)
            {
                throw new InvalidOperationException(
                    "ACS join is not configured. Set Acs__ConnectionString and MeetingBot__CallbackBaseUrl, " +
                    "or set MeetingBot__MeetingJoinBackend=Graph for Teams meetings.");
            }

            callId = await _acsJoin.JoinTeamsMeetingAsync(
                request.RoomId,
                request.MeetingJoinUrl,
                cancellationToken).ConfigureAwait(false);
            session.Events.Add(new CallEvent { EventType = "acs-call-created", Details = $"CallConnectionId={callId}" });
        }

        session.CallId = callId;
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

        try
        {
            if (IsAcsBackend(session))
            {
                await _acsActions.HangUpAsync(session.CallId, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await _graphCallsClient.EndCallAsync(session.CallId, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.NotFound && !IsAcsBackend(session))
        {
            _logger.LogInformation("Call {CallId} already ended when leave was requested.", session.CallId);
            session.Events.Add(new CallEvent { EventType = "call-end-already-ended", Details = "Graph returned 404 on end call" });
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Hang up / end call error for room {RoomId}", roomId);
        }

        session.Status = RoomStatus.Ended;
        session.EndedAtUtc = DateTimeOffset.UtcNow;
        session.LeaveReason = reason;
        session.Events.Add(new CallEvent { EventType = "call-ended", Details = reason });
        _store.Upsert(session);
        if (IsAcsBackend(session))
        {
            _acsRegistry.RemoveByRoom(roomId);
        }

        return true;
    }

    public async Task<TurnProcessingResult> SubmitTurnAsync(string roomId, SubmitTurnRequest request, CancellationToken cancellationToken)
    {
        if (!_store.TryGet(roomId, out var session) || session is null || string.IsNullOrWhiteSpace(session.CallId))
        {
            return new TurnProcessingResult(false, "Room not found or call not initialized.");
        }

        var transcript = (request.Transcript ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(transcript))
        {
            return new TurnProcessingResult(false, "Transcript is required.");
        }

        if (session.Status is RoomStatus.Ended or RoomStatus.Failed)
        {
            return new TurnProcessingResult(false, $"Room is not active (status={session.Status}).");
        }

        if (session.IsProcessingTurn)
        {
            return new TurnProcessingResult(false, "Another turn is currently being processed.");
        }

        var turnId = string.IsNullOrWhiteSpace(request.TurnId)
            ? $"turn-{session.NextTurnId++:0000}"
            : request.TurnId.Trim();
        var turnKey = $"{session.CallId}:{turnId}";
        if (session.ProcessedTurnKeys.Contains(turnKey))
        {
            session.Events.Add(new CallEvent { EventType = "turn-duplicate-ignored", Details = $"TurnId={turnId}" });
            _store.Upsert(session);
            return new TurnProcessingResult(true, "Duplicate turn ignored.", turnId, turnId);
        }

        session.IsProcessingTurn = true;
        session.ProcessedTurnKeys.Add(turnKey);
        session.LastUserUtterance = transcript;
        session.Events.Add(new CallEvent { EventType = "turn-received", Details = $"TurnId={turnId}; Transcript={transcript}" });
        _store.Upsert(session);

        try
        {
            var history = new List<string>();
            if (!string.IsNullOrWhiteSpace(session.LastBotReply))
            {
                history.Add(session.LastBotReply);
            }

            var turnResponse = await _aiBridgeClient.RequestTurnResponseAsync(
                roomId,
                session.CallId!,
                transcript,
                turnId,
                history,
                cancellationToken).ConfigureAwait(false);

            if (turnResponse is null)
            {
                return new TurnProcessingResult(false, "AI bridge did not return a response.", turnId, turnId);
            }

            session.LastTurnTraceId = turnResponse.TraceId;
            session.LastBotReply = turnResponse.ReplyText;
            _store.Upsert(session);

            if (string.IsNullOrWhiteSpace(turnResponse.AudioUri))
            {
                return new TurnProcessingResult(false, "TTS did not return audio URI.", turnId, turnResponse.TraceId);
            }

            var played = await TryPlayAudioWithRetryAsync(session, session.CallId!, turnResponse.AudioUri, turnId, cancellationToken)
                .ConfigureAwait(false);
            return played
                ? new TurnProcessingResult(true, "Turn processed and audio playback requested.", turnId, turnResponse.TraceId)
                : new TurnProcessingResult(false, "Failed to play turn audio.", turnId, turnResponse.TraceId);
        }
        finally
        {
            session.IsProcessingTurn = false;
            _store.Upsert(session);
        }
    }

    public async Task HandleCallbackAsync(string payload, CancellationToken cancellationToken)
    {
        var notifications = ParseCallNotifications(payload);
        if (notifications.Count == 0)
        {
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

            if (IsAcsBackend(session))
            {
                continue;
            }

            await RunEstablishedSessionFlowAsync(session, callId, cancellationToken).ConfigureAwait(false);
        }

        foreach (var notification in notifications.Where(n => n.IsTerminated))
        {
            var callId = notification.CallId;
            var session = string.IsNullOrWhiteSpace(callId) ? null : _store.FindByCallId(callId);
            if (session is null || IsAcsBackend(session))
            {
                continue;
            }

            session.Status = RoomStatus.Ended;
            session.EndedAtUtc = DateTimeOffset.UtcNow;
            session.LeaveReason ??= "terminated-callback";
            session.Events.Add(new CallEvent { EventType = "call-terminated-callback", Details = "Graph callback terminated" });
            _store.Upsert(session);
        }
    }

    public async Task RunAcsEstablishedFlowAsync(string roomId, string callConnectionId, CancellationToken cancellationToken)
    {
        if (!_store.TryGet(roomId, out var session) || session is null || !IsAcsBackend(session))
        {
            return;
        }

        session.CallId = callConnectionId;
        await RunEstablishedSessionFlowAsync(session, callConnectionId, cancellationToken).ConfigureAwait(false);
    }

    public async Task TryConsumeSttFinalAsync(string roomId, string transcript, CancellationToken cancellationToken)
    {
        if (!_store.TryGet(roomId, out var session) || session is null)
        {
            return;
        }

        if (session.Status is RoomStatus.Ended or RoomStatus.Leaving)
        {
            return;
        }

        if (session.SttSuppressedUntilUtc is { } sup && DateTimeOffset.UtcNow < sup)
        {
            return;
        }

        if (session.IsProcessingTurn)
        {
            return;
        }

        var t = transcript.Trim();
        if (t.Length < _options.SttMinTranscriptLength)
        {
            return;
        }

        var wordCount = t.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries).Length;
        if (wordCount < _options.SttMinWordCount)
        {
            return;
        }

        if (session.LastSttForwardedAtUtc is { } la &&
            session.LastSttForwardedText is { } lx &&
            (DateTimeOffset.UtcNow - la) < TimeSpan.FromSeconds(4) &&
            string.Equals(lx, t, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(session.LastBotReply) &&
            t.Length <= session.LastBotReply.Length + 12 &&
            session.LastBotReply.Contains(t, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        session.LastSttForwardedText = t;
        session.LastSttForwardedAtUtc = DateTimeOffset.UtcNow;
        session.Events.Add(new CallEvent { EventType = "stt-final-received", Details = t });
        _store.Upsert(session);

        await HandleFinalTranscriptAsync(roomId, t, cancellationToken).ConfigureAwait(false);
    }

    private async Task RunEstablishedSessionFlowAsync(
        RoomSession session,
        string callConnectionId,
        CancellationToken cancellationToken)
    {
        if (!session.Events.Any(e => e.EventType == "call-established"))
        {
            session.Status = RoomStatus.Established;
            session.Events.Add(new CallEvent
            {
                EventType = "call-established",
                Details = IsAcsBackend(session) ? "ACS CallConnected" : "Graph callback established"
            });
            _store.Upsert(session);
        }

        var greetingRequested = session.Events.Any(e =>
            e.EventType is "greeting-play-requested" or "greeting-playprompt-requested");
        if (!greetingRequested)
        {
            var audioUri = await _aiBridgeClient.RequestFixedPhraseAsync(
                session.RoomId,
                callConnectionId,
                _options.FixedGreetingLine,
                cancellationToken).ConfigureAwait(false);

            session.Events.Add(
                new CallEvent
                {
                    EventType = "fixed-line-ready",
                    Details = audioUri is null ? "No TTS URI" : $"AudioUri={audioUri}"
                });
            _store.Upsert(session);

            if (!string.IsNullOrWhiteSpace(audioUri))
            {
                await TryPlayGreetingWithRetryAsync(session, callConnectionId, audioUri, cancellationToken).ConfigureAwait(false);
            }
        }

        if (!session.Events.Any(e => e.EventType == "auto-leave-scheduled") && _options.AutoLeaveSeconds > 0)
        {
            session.Events.Add(new CallEvent { EventType = "auto-leave-scheduled", Details = $"Delay={_options.AutoLeaveSeconds}s" });
            _store.Upsert(session);

            _ = Task.Run(
                async () =>
                {
                    try
                    {
                        await Task.Delay(TimeSpan.FromSeconds(_options.AutoLeaveSeconds), cancellationToken).ConfigureAwait(false);
                        await LeaveAsync(session.RoomId, "auto-leave-timer", cancellationToken).ConfigureAwait(false);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Auto-leave failed for room {RoomId}", session.RoomId);
                    }
                },
                cancellationToken);
        }
    }

    private Task TryPlayGreetingWithRetryAsync(
        RoomSession session,
        string callId,
        string audioUri,
        CancellationToken cancellationToken) =>
        IsAcsBackend(session)
            ? TryPlayAcsGreetingWithRetryAsync(session, callId, audioUri, cancellationToken)
            : TryPlayGraphGreetingWithRetryAsync(session, callId, audioUri, cancellationToken);

    private async Task TryPlayAcsGreetingWithRetryAsync(
        RoomSession session,
        string callConnectionId,
        string audioUri,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var delay = TimeSpan.FromSeconds(2);

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                session.Events.Add(new CallEvent { EventType = "greeting-play-requested", Details = $"Attempt={attempt}" });
                _store.Upsert(session);
                await _acsActions.PlayAudioUriAsync(callConnectionId, audioUri, cancellationToken).ConfigureAwait(false);
                ArmSttSuppression(session);
                return;
            }
            catch (Exception ex) when (attempt < maxAttempts)
            {
                _logger.LogInformation(ex, "ACS greeting play deferred attempt {Attempt} room {RoomId}", attempt, session.RoomId);
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "ACS greeting play failed room {RoomId}", session.RoomId);
                session.Events.Add(new CallEvent { EventType = "greeting-play-failed", Details = ex.Message });
                _store.Upsert(session);
                return;
            }
        }
    }

    private async Task TryPlayGraphGreetingWithRetryAsync(
        RoomSession session,
        string callId,
        string audioUri,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var delay = TimeSpan.FromSeconds(2);
        Exception? lastException = null;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                await _graphCallsClient.PlayPromptAsync(callId, audioUri, cancellationToken).ConfigureAwait(false);
                session.Events.Add(new CallEvent
                {
                    EventType = "greeting-playprompt-requested",
                    Details = $"Requested Graph playPrompt on attempt {attempt}"
                });
                ArmSttSuppression(session);
                _store.Upsert(session);
                return;
            }
            catch (Exception ex) when (IsNotEstablishedPlayPromptError(ex) && attempt < maxAttempts)
            {
                lastException = ex;
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                lastException = ex;
                break;
            }
        }

        if (lastException is not null)
        {
            _logger.LogWarning(lastException, "Graph playPrompt failed for room {RoomId} call {CallId}", session.RoomId, callId);
            session.Events.Add(new CallEvent { EventType = "greeting-playprompt-failed", Details = lastException.Message });
            _store.Upsert(session);
        }
    }

    private Task<bool> TryPlayAudioWithRetryAsync(
        RoomSession session,
        string callId,
        string audioUri,
        string turnId,
        CancellationToken cancellationToken) =>
        IsAcsBackend(session)
            ? TryPlayAcsAudioWithRetryAsync(session, callId, audioUri, turnId, cancellationToken)
            : TryPlayGraphAudioWithRetryAsync(session, callId, audioUri, turnId, cancellationToken);

    private async Task<bool> TryPlayAcsAudioWithRetryAsync(
        RoomSession session,
        string callConnectionId,
        string audioUri,
        string turnId,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var delay = TimeSpan.FromSeconds(2);

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                session.Events.Add(new CallEvent { EventType = "acs-play-requested", Details = $"TurnId={turnId}; Attempt={attempt}" });
                _store.Upsert(session);
                await _acsActions.PlayAudioUriAsync(callConnectionId, audioUri, cancellationToken).ConfigureAwait(false);
                ArmSttSuppression(session);
                return true;
            }
            catch (Exception ex) when (attempt < maxAttempts)
            {
                _logger.LogInformation(ex, "ACS play deferred attempt {Attempt} room {RoomId}", attempt, session.RoomId);
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "ACS play failed room {RoomId} turn {TurnId}", session.RoomId, turnId);
                session.Events.Add(new CallEvent { EventType = "acs-play-failed", Details = ex.Message });
                _store.Upsert(session);
                return false;
            }
        }

        return false;
    }

    private async Task<bool> TryPlayGraphAudioWithRetryAsync(
        RoomSession session,
        string callId,
        string audioUri,
        string turnId,
        CancellationToken cancellationToken)
    {
        const int maxAttempts = 5;
        var delay = TimeSpan.FromSeconds(2);
        Exception? lastException = null;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                session.Events.Add(new CallEvent { EventType = "playprompt-requested", Details = $"TurnId={turnId}; Attempt={attempt}" });
                _store.Upsert(session);
                await _graphCallsClient.PlayPromptAsync(callId, audioUri, cancellationToken).ConfigureAwait(false);
                session.Events.Add(new CallEvent { EventType = "playprompt-completed", Details = $"TurnId={turnId}; Attempt={attempt}" });
                ArmSttSuppression(session);
                _store.Upsert(session);
                return true;
            }
            catch (Exception ex) when (IsNotEstablishedPlayPromptError(ex) && attempt < maxAttempts)
            {
                lastException = ex;
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                lastException = ex;
                break;
            }
        }

        if (lastException is not null)
        {
            session.Events.Add(new CallEvent { EventType = "playprompt-failed", Details = $"TurnId={turnId}; {lastException.Message}" });
            _store.Upsert(session);
        }

        return false;
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
                        const string marker = "/communications/calls/";
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
            return [];
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

    private static bool IsNotEstablishedPlayPromptError(Exception ex)
    {
        if (ex is not HttpRequestException httpEx || string.IsNullOrWhiteSpace(httpEx.Message))
        {
            return false;
        }

        return httpEx.Message.Contains("\"code\":\"8501\"", StringComparison.OrdinalIgnoreCase) ||
               httpEx.Message.Contains("not in Established state", StringComparison.OrdinalIgnoreCase);
    }

    private void ArmSttSuppression(RoomSession session)
    {
        if (_options.SttSuppressionAfterPlaySeconds <= 0)
        {
            return;
        }

        session.SttSuppressedUntilUtc = DateTimeOffset.UtcNow.AddSeconds(_options.SttSuppressionAfterPlaySeconds);
    }
}
