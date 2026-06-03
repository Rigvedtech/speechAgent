using System.Text.Json;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services.Acs;

/// <summary>Joins a Teams meeting via ACS Call Automation REST (teamsMeetingLink target).</summary>
public sealed class AcsCallJoinService
{
    private readonly AcsOptions _acs;
    private readonly MeetingBotOptions _meeting;
    private readonly AcsBotIdentityService _identity;
    private readonly AcsCallRegistry _registry;
    private readonly ILogger<AcsCallJoinService> _logger;

    public AcsCallJoinService(
        IOptions<AcsOptions> acs,
        IOptions<MeetingBotOptions> meeting,
        AcsBotIdentityService identity,
        AcsCallRegistry registry,
        ILogger<AcsCallJoinService> logger)
    {
        _acs = acs.Value;
        _meeting = meeting.Value;
        _identity = identity;
        _registry = registry;
        _logger = logger;
    }

    public bool IsConfigured => _acs.IsConfigured && !string.IsNullOrWhiteSpace(_meeting.CallbackBaseUrl);

    public async Task<string> JoinTeamsMeetingAsync(string roomId, string meetingJoinUrl, CancellationToken cancellationToken)
    {
        if (!IsConfigured)
        {
            throw new InvalidOperationException(
                "ACS join is not configured. Set Acs__ConnectionString and MeetingBot__CallbackBaseUrl (public HTTPS).");
        }

        var meetingLink = meetingJoinUrl.Trim();
        var botUserId = await _identity.GetOrCreateBotUserIdAsync(cancellationToken).ConfigureAwait(false);

        var callbackUri = $"{_meeting.CallbackBaseUrl.TrimEnd('/')}{_acs.EventsCallbackPath}";
        var mediaTransportUri = BuildMediaWebSocketUri();

        var payload = new Dictionary<string, object?>
        {
            ["targets"] = new object[]
            {
                new Dictionary<string, object?>
                {
                    ["kind"] = "teamsMeetingLink",
                    ["teamsMeetingLink"] = new Dictionary<string, object?> { ["meetingLink"] = meetingLink }
                }
            },
            ["source"] = new Dictionary<string, object?>
            {
                ["kind"] = "communicationUser",
                ["communicationUser"] = new Dictionary<string, object?> { ["id"] = botUserId }
            },
            ["sourceDisplayName"] = _acs.BotDisplayName,
            ["callbackUri"] = callbackUri,
            ["operationContext"] = roomId,
            ["mediaStreamingOptions"] = new Dictionary<string, object?>
            {
                ["transportUrl"] = mediaTransportUri,
                ["transportType"] = "websocket",
                ["contentType"] = "audio",
                ["audioChannelType"] = "mixed",
                ["startMediaStreaming"] = true,
                ["enableBidirectional"] = true,
                ["audioFormat"] = "pcm16KMono"
            }
        };

        var json = JsonSerializer.Serialize(payload);
        var path = $"/calling/callConnections?api-version={_acs.ApiVersion}";

        _logger.LogDebug(
            "ACS create call request. Path={Path} Callback={Callback} MediaWs={MediaWs} PayloadBytes={Bytes}",
            path,
            callbackUri,
            mediaTransportUri,
            json.Length);

        var (status, body) = await AcsHmacRestClient.PostJsonAsync(
            _acs.ConnectionString,
            path,
            json,
            cancellationToken).ConfigureAwait(false);

        if (status is < 200 or >= 300)
        {
            _logger.LogError("ACS create call failed. Status={Status} Body={Body}", status, body);
            throw new HttpRequestException(
                $"ACS create call failed with status {status}. Body: {body}",
                null,
                (System.Net.HttpStatusCode)status);
        }

        using var doc = JsonDocument.Parse(body);
        var callConnectionId = doc.RootElement.TryGetProperty("callConnectionId", out var idEl)
            ? idEl.GetString()
            : null;

        if (string.IsNullOrWhiteSpace(callConnectionId))
        {
            throw new InvalidOperationException($"ACS create call response missing callConnectionId. Body: {body}");
        }

        _registry.Register(roomId, callConnectionId);
        _logger.LogInformation(
            "ACS call created. Room={RoomId} CallConnectionId={CallId} MediaWs={MediaUri}",
            roomId,
            callConnectionId,
            mediaTransportUri);

        return callConnectionId;
    }

    private string BuildMediaWebSocketUri()
    {
        var baseUrl = _meeting.CallbackBaseUrl.Trim();
        if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var httpsUri))
        {
            throw new InvalidOperationException($"MeetingBot:CallbackBaseUrl is not a valid absolute URI: {baseUrl}");
        }

        var scheme = string.Equals(httpsUri.Scheme, "https", StringComparison.OrdinalIgnoreCase) ? "wss" : "ws";
        var builder = new UriBuilder(httpsUri)
        {
            Scheme = scheme,
            Path = _acs.MediaWebSocketPath,
            Query = string.Empty
        };
        return builder.Uri.ToString();
    }
}
