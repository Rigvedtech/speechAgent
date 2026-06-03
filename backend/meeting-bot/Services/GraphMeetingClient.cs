using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace MeetingBot.Services;

/// <summary>Graph Calendar API only (onlineMeetings). Join/media uses ACS.</summary>
public sealed class GraphMeetingClient
{
    private sealed record CreatedMeeting(string Id, string JoinWebUrl, DateTimeOffset StartDateTime, DateTimeOffset EndDateTime);

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly GraphTokenProvider _tokenProvider;
    private readonly ILogger<GraphMeetingClient> _logger;

    public GraphMeetingClient(
        IHttpClientFactory httpClientFactory,
        GraphTokenProvider tokenProvider,
        ILogger<GraphMeetingClient> logger)
    {
        _httpClientFactory = httpClientFactory;
        _tokenProvider = tokenProvider;
        _logger = logger;
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
        var client = _httpClientFactory.CreateClient(nameof(GraphMeetingClient));
        using var response = await client.SendAsync(request, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            _logger.LogError(
                "Graph create onlineMeeting failed. Status: {StatusCode}. Body: {Body}",
                (int)response.StatusCode,
                body);
            throw new HttpRequestException(
                $"Graph create onlineMeeting failed with status {(int)response.StatusCode}. Body: {body}",
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
}
