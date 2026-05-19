using System.Text.Json;
using System.Net;
using MeetingBot.Models.Domain;
using MeetingBot.Models.Options;
using MeetingBot.Models.Requests;
using MeetingBot.Services.Comms;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class CallLifecycleService
{
    private sealed record CallNotification(string CallId, bool IsEstablished, bool IsTerminated);
    public sealed record TurnProcessingResult(bool Success, string Message, string? TurnId = null, string? TraceId = null);

    private readonly GraphCallsClient _graphCallsClient;
    private readonly RoomSessionStore _store;
    private readonly AiBridgeClient _aiBridgeClient;
    private readonly ISttVoiceLoopStarter _sttVoiceLoopStarter;
    private readonly TeamsCommunicationsService _comms;
    private readonly ILogger<CallLifecycleService> _logger;
    private readonly MeetingBotOptions _options;

    public CallLifecycleService(
        GraphCallsClient graphCallsClient,
        RoomSessionStore store,
        AiBridgeClient aiBridgeClient,
        ISttVoiceLoopStarter sttVoiceLoopStarter,
        TeamsCommunicationsService comms,
        IOptions<MeetingBotOptions> options,
        ILogger<CallLifecycleService> logger)
    {
        _graphCallsClient = graphCallsClient;
        _store = store;
        _aiBridgeClient = aiBridgeClient;
        _sttVoiceLoopStarter = sttVoiceLoopStarter;
        _comms = comms;
        _logger = logger;
        _options = options.Value;
    }

    // Phase-3 wiring note:
    // Actual Teams audio ingestion requires the application-hosted media pipeline (Graph Communications Calling SDK).
    // This method is the orchestration hook we will call from the media receive loop once PCM frames arrive.
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
        session.Events.Add(new CallEvent { EventType = "start-requested", Details = "Start endpoint triggered" });
        _store.Upsert(session);

        string callId;
        if (_comms.IsEnabled)
        {
            session.Events.Add(new CallEvent { EventType = "join-via-comms-sdk", Details = "Application-hosted media join" });
            _store.Upsert(session);
            callId = await _comms.JoinMeetingAsync(request.RoomId, request.MeetingJoinUrl, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            if (_options.UseApplicationHostedMedia)
            {
                throw new InvalidOperationException(
                    "MeetingBot:UseApplicationHostedMedia is true but the Communications client failed to start. " +
                    "Complete MediaPlatform settings (certificate, ports, public IP, ServiceFqdn) or set UseApplicationHostedMedia=false.");
            }

            callId = await _graphCallsClient.CreateMeetingCallAsync(request.MeetingJoinUrl, cancellationToken).ConfigureAwait(false);
        }

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

        await _sttVoiceLoopStarter.StopAsync(roomId, cancellationToken).ConfigureAwait(false);

        session.Status = RoomStatus.Leaving;
        session.Events.Add(new CallEvent { EventType = "leave-requested", Details = reason });
        _store.Upsert(session);

        try
        {
            if (_comms.IsEnabled)
            {
                await _comms.TryDeleteCallAsync(session.CallId, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await _graphCallsClient.EndCallAsync(session.CallId, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
        {
            // Idempotent leave: call may already be ended by callback/manual leave.
            _logger.LogInformation("Call {CallId} already ended when leave was requested.", session.CallId);
            session.Events.Add(new CallEvent { EventType = "call-end-already-ended", Details = "Graph returned 404 on end call" });
        }
        session.Status = RoomStatus.Ended;
        session.EndedAtUtc = DateTimeOffset.UtcNow;
        session.LeaveReason = reason;
        session.Events.Add(new CallEvent { EventType = "call-ended", Details = reason });
        _store.Upsert(session);
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
            session.Events.Add(new CallEvent { EventType = "stt-ready", Details = $"TurnId={turnId}; Transcript={transcript}" });
            _store.Upsert(session);

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
                cancellationToken);

            if (turnResponse is null)
            {
                session.Events.Add(new CallEvent { EventType = "turn-processing-failed", Details = $"TurnId={turnId}; AI bridge returned null response." });
                _store.Upsert(session);
                return new TurnProcessingResult(false, "AI bridge did not return a response.", turnId, turnId);
            }

            session.LastTurnTraceId = turnResponse.TraceId;
            session.LastBotReply = turnResponse.ReplyText;
            session.Events.Add(
                new CallEvent
                {
                    EventType = "llm-reply-ready",
                    Details = $"TurnId={turnId}; TraceId={turnResponse.TraceId}; Reply={turnResponse.ReplyText}"
                });
            session.Events.Add(
                new CallEvent
                {
                    EventType = "tts-audio-ready",
                    Details = string.IsNullOrWhiteSpace(turnResponse.AudioUri)
                        ? $"TurnId={turnId}; No audio URI returned."
                        : $"TurnId={turnId}; AudioUri={turnResponse.AudioUri}; LatencyMs={turnResponse.LatencyMs}"
                });
            _store.Upsert(session);

            if (string.IsNullOrWhiteSpace(turnResponse.AudioUri))
            {
                return new TurnProcessingResult(false, "TTS did not return audio URI.", turnId, turnResponse.TraceId);
            }

            var played = await TryPlayPromptWithRetryAsync(
                session,
                session.CallId!,
                turnResponse.AudioUri!,
                turnId,
                cancellationToken);

            if (played)
            {
                session.LastPlayPromptAtUtc = DateTimeOffset.UtcNow;
                _store.Upsert(session);
                return new TurnProcessingResult(true, "Turn played successfully.", turnId, turnResponse.TraceId);
            }

            return new TurnProcessingResult(false, "Failed to play turn audio.", turnId, turnResponse.TraceId);
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

            await RunEstablishedSessionFlowAsync(session, callId, startLocalSttAfterGreeting: !_comms.IsEnabled, cancellationToken)
                .ConfigureAwait(false);
        }

        foreach (var notification in notifications.Where(n => n.IsTerminated))
        {
            var callId = notification.CallId;
            var session = string.IsNullOrWhiteSpace(callId) ? null : _store.FindByCallId(callId);
            if (session is not null)
            {
                await _sttVoiceLoopStarter.StopAsync(session.RoomId, cancellationToken).ConfigureAwait(false);

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
                ArmSttSuppression(session);
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

    private async Task<bool> TryPlayPromptWithRetryAsync(
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
                await _graphCallsClient.PlayPromptAsync(callId, audioUri, cancellationToken);
                session.Events.Add(new CallEvent { EventType = "playprompt-completed", Details = $"TurnId={turnId}; Attempt={attempt}" });
                ArmSttSuppression(session);
                _store.Upsert(session);
                return true;
            }
            catch (Exception ex) when (IsNotEstablishedPlayPromptError(ex) && attempt < maxAttempts)
            {
                lastException = ex;
                _logger.LogInformation(
                    "turn playPrompt attempt {Attempt}/{MaxAttempts} deferred for room {RoomId} call {CallId}: call not established yet.",
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
            session.Events.Add(new CallEvent { EventType = "playprompt-failed", Details = $"TurnId={turnId}; {lastException.Message}" });
            _store.Upsert(session);
            _logger.LogWarning(lastException, "Turn playPrompt failed for room {RoomId} call {CallId}", session.RoomId, callId);
        }
        return false;
    }

    /// <summary>Invoked when an app-hosted media call becomes established.</summary>
    public async Task OnAppHostedCallEstablishedAsync(string callId, CancellationToken cancellationToken)
    {
        var session = _store.FindByCallId(callId);
        if (session is null)
        {
            _logger.LogWarning("App-hosted call {CallId} established but no room session is registered.", callId);
            return;
        }

        await RunEstablishedSessionFlowAsync(session, callId, startLocalSttAfterGreeting: false, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Shared gate for STT finals from loopback/mic or in-call media before turn processing.</summary>
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
            _logger.LogInformation("STT final dropped (suppressed until {Until:o}) room={RoomId} text={Text}", sup, roomId, transcript);
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
            _logger.LogDebug("STT final dropped (min words {Need}) room={RoomId} text={Text}", _options.SttMinWordCount, roomId, t);
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
            _logger.LogDebug("STT skipped as likely bot-playback echo room={RoomId}", roomId);
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
        string callId,
        bool startLocalSttAfterGreeting,
        CancellationToken cancellationToken)
    {
        var alreadyEstablished = session.Events.Any(e => e.EventType == "call-established");
        if (!alreadyEstablished)
        {
            session.Status = RoomStatus.Established;
            session.Events.Add(new CallEvent { EventType = "call-established", Details = "Callback state established" });
            _store.Upsert(session);
        }

        var alreadyRequestedGreeting = session.Events.Any(e => e.EventType == "greeting-playprompt-requested");
        if (!alreadyRequestedGreeting)
        {
            var audioUri = await _aiBridgeClient.RequestFixedPhraseAsync(
                session.RoomId,
                callId,
                _options.FixedGreetingLine,
                cancellationToken).ConfigureAwait(false);
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
                await TryPlayGreetingWithRetryAsync(session, callId, audioUri, cancellationToken).ConfigureAwait(false);
            }
        }

        if (startLocalSttAfterGreeting)
        {
            _sttVoiceLoopStarter.RequestStartAfterGreeting(session.RoomId);
        }

        var alreadyScheduledAutoLeave = session.Events.Any(e => e.EventType == "auto-leave-scheduled");
        if (!alreadyScheduledAutoLeave && _options.AutoLeaveSeconds > 0)
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
                        _logger.LogWarning(ex, "Auto-leave timer failed for room {RoomId}", session.RoomId);
                    }
                },
                cancellationToken);
        }
    }

    private void ArmSttSuppression(RoomSession session)
    {
        if (_options.SttSuppressionAfterPlaySeconds <= 0)
        {
            return;
        }

        session.SttSuppressedUntilUtc = DateTimeOffset.UtcNow.AddSeconds(_options.SttSuppressionAfterPlaySeconds);
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
