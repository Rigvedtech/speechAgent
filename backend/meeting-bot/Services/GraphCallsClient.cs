using System.Text;
using System.Text.Json;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Logging;

namespace MeetingBot.Services;

public sealed class GraphCallsClient
{
    private sealed record CreatedMeeting(string Id, string JoinWebUrl, DateTimeOffset StartDateTime, DateTimeOffset EndDateTime);
    private sealed record MeetingJoinContext(string Tid, string Oid, string ThreadId, string MessageId);
    private sealed record MediaInfo(string Uri);
    private sealed record MediaPrompt(MediaInfo MediaInfo);
    private sealed record PlayPromptRequest(MediaPrompt[] Prompts);

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly GraphTokenProvider _tokenProvider;
    private readonly GraphOptions _graphOptions;
    private readonly MeetingBotOptions _botOptions;
    private readonly ILogger<GraphCallsClient> _logger;

    public GraphCallsClient(
        IHttpClientFactory httpClientFactory,
        GraphTokenProvider tokenProvider,
        IOptions<GraphOptions> graphOptions,
        IOptions<MeetingBotOptions> botOptions,
        ILogger<GraphCallsClient> logger)
    {
        _httpClientFactory = httpClientFactory;
        _tokenProvider = tokenProvider;
        _graphOptions = graphOptions.Value;
        _botOptions = botOptions.Value;
        _logger = logger;
    }

    public async Task<string> CreateMeetingCallAsync(string meetingJoinUrl, CancellationToken cancellationToken)
    {
        var ctx = ExtractMeetingJoinContext(meetingJoinUrl);
        using var request = await _tokenProvider.CreateGraphRequestAsync(HttpMethod.Post, "/communications/calls", cancellationToken);
        var callbackUri = $"{_botOptions.CallbackBaseUrl.TrimEnd('/')}/api/calls/callback";

        // Build Graph payload for creating/joining a call into an existing organizer meeting.
        // We extract the organizer identity + thread/message context from the Teams join URL.
        var createCallPayload = new Dictionary<string, object?>
        {
            ["callbackUri"] = callbackUri,
            ["requestedModalities"] = new[] { "audio" },
            ["mediaConfig"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.serviceHostedMediaConfig"
            },
            ["chatInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.chatInfo",
                ["threadId"] = ctx.ThreadId,
                ["messageId"] = ctx.MessageId
            },
            ["meetingInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.organizerMeetingInfo",
                ["joinWebUrl"] = meetingJoinUrl,
                ["organizer"] = new Dictionary<string, object?>
                {
                    ["@odata.type"] = "#microsoft.graph.identitySet",
                    ["user"] = new Dictionary<string, object?>
                    {
                        ["@odata.type"] = "#microsoft.graph.identity",
                        ["id"] = ctx.Oid,
                        ["tenantId"] = ctx.Tid
                    }
                }
            },
            // Use tenant from join URL context to ensure strict tenant alignment.
            ["tenantId"] = ctx.Tid
        };

        request.Content = new StringContent(JsonSerializer.Serialize(createCallPayload), Encoding.UTF8, "application/json");
        var client = _httpClientFactory.CreateClient(nameof(GraphCallsClient));
        using var response = await client.SendAsync(request, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            _logger.LogError(
                "Graph create call failed. Status: {StatusCode}. Response body: {GraphResponseBody}",
                (int)response.StatusCode,
                body);

            throw new HttpRequestException(
                $"Graph create call failed with status {(int)response.StatusCode} ({response.ReasonPhrase}). Graph body: {body}",
                null,
                response.StatusCode);
        }

        using var json = JsonDocument.Parse(body);
        return json.RootElement.GetProperty("id").GetString() ?? string.Empty;
    }

    private static MeetingJoinContext ExtractMeetingJoinContext(string meetingJoinUrl)
    {
        if (string.IsNullOrWhiteSpace(meetingJoinUrl))
        {
            throw new ArgumentException("meetingJoinUrl is required.", nameof(meetingJoinUrl));
        }

        var uri = new Uri(meetingJoinUrl);

        // 1) Extract Tid/Oid from the `context` query param (URL-decoded JSON).
        string contextJson = string.Empty;
        foreach (var part in uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var kv = part.Split('=', 2);
            if (kv.Length == 2 && kv[0].Equals("context", StringComparison.OrdinalIgnoreCase))
            {
                contextJson = Uri.UnescapeDataString(kv[1]);
                break;
            }
        }

        if (string.IsNullOrWhiteSpace(contextJson))
        {
            throw new ArgumentException("meetingJoinUrl is missing required `context` query parameter.", nameof(meetingJoinUrl));
        }

        using var ctxDoc = JsonDocument.Parse(contextJson);
        var tid = ctxDoc.RootElement.GetProperty("Tid").GetString() ?? string.Empty;
        var oid = ctxDoc.RootElement.GetProperty("Oid").GetString() ?? string.Empty;

        // 2) Extract threadId/messageId from path: .../meetup-join/{threadIdEncoded}/{messageId}
        var segments = uri.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length < 2)
        {
            throw new ArgumentException("meetingJoinUrl has an unexpected path format.", nameof(meetingJoinUrl));
        }

        var messageId = segments[^1];
        var threadIdEncoded = segments[^2];
        var threadId = Uri.UnescapeDataString(threadIdEncoded);

        if (string.IsNullOrWhiteSpace(tid) || string.IsNullOrWhiteSpace(oid) ||
            string.IsNullOrWhiteSpace(threadId) || string.IsNullOrWhiteSpace(messageId))
        {
            throw new ArgumentException("meetingJoinUrl context extraction failed.", nameof(meetingJoinUrl));
        }

        return new MeetingJoinContext(tid, oid, threadId, messageId);
    }

    public async Task<(string MeetingId, string JoinWebUrl, DateTimeOffset StartDateTimeUtc, DateTimeOffset EndDateTimeUtc)> CreateOnlineMeetingAsync(
        string organizerUserIdOrUpn,
        string subject,
        DateTimeOffset startDateTimeUtc,
        DateTimeOffset endDateTimeUtc,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(organizerUserIdOrUpn))
        {
            throw new ArgumentException("Organizer user id or UPN is required.", nameof(organizerUserIdOrUpn));
        }

        if (endDateTimeUtc <= startDateTimeUtc)
        {
            throw new ArgumentException("End datetime must be greater than start datetime.");
        }

        var relativeUri = $"/users/{Uri.EscapeDataString(organizerUserIdOrUpn)}/onlineMeetings";
        using var request = await _tokenProvider.CreateGraphRequestAsync(HttpMethod.Post, relativeUri, cancellationToken);
        var payload = new Dictionary<string, object?>
        {
            ["startDateTime"] = startDateTimeUtc.UtcDateTime.ToString("o"),
            ["endDateTime"] = endDateTimeUtc.UtcDateTime.ToString("o"),
            ["subject"] = subject
        };

        request.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
        var client = _httpClientFactory.CreateClient(nameof(GraphCallsClient));
        using var response = await client.SendAsync(request, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            _logger.LogError(
                "Graph create onlineMeeting failed. Status: {StatusCode}. Response body: {GraphResponseBody}",
                (int)response.StatusCode,
                body);

            throw new HttpRequestException(
                $"Graph create onlineMeeting failed with status {(int)response.StatusCode} ({response.ReasonPhrase}). Graph body: {body}",
                null,
                response.StatusCode);
        }

        var created = JsonSerializer.Deserialize<CreatedMeeting>(
            body,
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

        if (created is null || string.IsNullOrWhiteSpace(created.JoinWebUrl))
        {
            throw new InvalidOperationException("Graph online meeting response is missing joinWebUrl.");
        }

        return (created.Id, created.JoinWebUrl, created.StartDateTime, created.EndDateTime);
    }

    public async Task EndCallAsync(string callId, CancellationToken cancellationToken)
    {
        using var request = await _tokenProvider.CreateGraphRequestAsync(HttpMethod.Delete, $"/communications/calls/{callId}", cancellationToken);
        var client = _httpClientFactory.CreateClient(nameof(GraphCallsClient));
        using var response = await client.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public async Task PlayPromptAsync(string callId, string mediaUri, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(callId))
        {
            throw new ArgumentException("callId is required.", nameof(callId));
        }

        if (string.IsNullOrWhiteSpace(mediaUri))
        {
            throw new ArgumentException("mediaUri is required.", nameof(mediaUri));
        }

        // Graph action: POST /communications/calls/{id}/playPrompt
        // Prompts array contains one mediaPrompt with mediaInfo.uri pointing at a WAV file.
        var payload = new Dictionary<string, object?>
        {
            ["prompts"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["@odata.type"] = "#microsoft.graph.mediaPrompt",
                    ["mediaInfo"] = new Dictionary<string, object?>
                    {
                        ["@odata.type"] = "#microsoft.graph.mediaInfo",
                        ["uri"] = mediaUri
                    }
                }
            }
        };

        using var request = await _tokenProvider.CreateGraphRequestAsync(
            HttpMethod.Post,
            $"/communications/calls/{callId}/playPrompt",
            cancellationToken);

        request.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");

        var client = _httpClientFactory.CreateClient(nameof(GraphCallsClient));
        using var response = await client.SendAsync(request, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogError(
                "Graph playPrompt failed. Status: {StatusCode}. Response body: {GraphResponseBody}",
                (int)response.StatusCode,
                body);

            throw new HttpRequestException(
                $"Graph playPrompt failed with status {(int)response.StatusCode} ({response.ReasonPhrase}). Graph body: {body}",
                null,
                response.StatusCode);
        }
    }
}
