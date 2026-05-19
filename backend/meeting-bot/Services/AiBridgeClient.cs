using System.Text;
using System.Text.Json;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class AiBridgeClient
{
    public sealed record TurnResponse(
        string ReplyText,
        string? AudioUri,
        string TraceId,
        int? LatencyMs);

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly AiBridgeOptions _options;
    private readonly ILogger<AiBridgeClient> _logger;

    public AiBridgeClient(
        IHttpClientFactory httpClientFactory,
        IOptions<AiBridgeOptions> options,
        ILogger<AiBridgeClient> logger)
    {
        _httpClientFactory = httpClientFactory;
        _options = options.Value;
        _logger = logger;
    }

    public bool Enabled => _options.Enabled;

    public async Task<string?> RequestFixedPhraseAsync(string roomId, string callId, string phrase, CancellationToken cancellationToken)
    {
        if (!Enabled)
        {
            return null;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_options.BaseUrl.TrimEnd('/')}/v1/interview/fixed-line");
        request.Content = new StringContent(
            JsonSerializer.Serialize(new { room_id = roomId, call_id = callId, phrase }),
            Encoding.UTF8,
            "application/json");

        var response = await SendWithRetryAsync(request, cancellationToken);
        if (response is null)
        {
            return null;
        }

        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var json = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
        return json.RootElement.TryGetProperty("audio_uri", out var value) ? value.GetString() : null;
    }

    public async Task<TurnResponse?> RequestTurnResponseAsync(
        string roomId,
        string callId,
        string transcript,
        string turnId,
        IReadOnlyList<string> history,
        CancellationToken cancellationToken)
    {
        if (!Enabled)
        {
            return null;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{_options.BaseUrl.TrimEnd('/')}/v1/interview/respond");
        request.Content = new StringContent(
            JsonSerializer.Serialize(new
            {
                room_id = roomId,
                call_id = callId,
                transcript,
                turn_id = turnId,
                history
            }),
            Encoding.UTF8,
            "application/json");

        var response = await SendWithRetryAsync(request, cancellationToken);
        if (response is null)
        {
            return null;
        }

        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var json = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);

        var replyText = json.RootElement.TryGetProperty("reply_text", out var replyValue)
            ? replyValue.GetString() ?? string.Empty
            : string.Empty;
        var audioUri = json.RootElement.TryGetProperty("audio_uri", out var uriValue)
            ? uriValue.GetString()
            : null;
        var traceId = json.RootElement.TryGetProperty("trace_id", out var traceValue)
            ? traceValue.GetString() ?? turnId
            : turnId;
        int? latencyMs = null;
        if (json.RootElement.TryGetProperty("latency_ms", out var latencyValue) &&
            latencyValue.ValueKind == JsonValueKind.Number &&
            latencyValue.TryGetInt32(out var parsedLatency))
        {
            latencyMs = parsedLatency;
        }

        return new TurnResponse(replyText, audioUri, traceId, latencyMs);
    }

    private async Task<HttpResponseMessage?> SendWithRetryAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient(nameof(AiBridgeClient));
        client.Timeout = TimeSpan.FromSeconds(Math.Max(5, _options.TimeoutSeconds));
        const int maxAttempts = 3;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            using var retryRequest = await CloneRequestAsync(request, cancellationToken);
            var response = await client.SendAsync(retryRequest, cancellationToken);
            if (response.IsSuccessStatusCode)
            {
                return response;
            }

            if ((int)response.StatusCode is >= 500 and < 600 && attempt < maxAttempts)
            {
                _logger.LogWarning(
                    "AI bridge request attempt {Attempt}/{MaxAttempts} failed with {StatusCode}; retrying.",
                    attempt,
                    maxAttempts,
                    (int)response.StatusCode);
                response.Dispose();
                await Task.Delay(TimeSpan.FromMilliseconds(200 * attempt), cancellationToken);
                continue;
            }

            _logger.LogWarning("AI bridge request failed with status {StatusCode}", response.StatusCode);
            response.Dispose();
            return null;
        }

        return null;
    }

    private static async Task<HttpRequestMessage> CloneRequestAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var clone = new HttpRequestMessage(request.Method, request.RequestUri);
        foreach (var header in request.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        if (request.Content is not null)
        {
            var body = await request.Content.ReadAsStringAsync(cancellationToken);
            clone.Content = new StringContent(body, Encoding.UTF8, request.Content.Headers.ContentType?.MediaType ?? "application/json");
            foreach (var header in request.Content.Headers)
            {
                if (header.Key.Equals("Content-Type", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }
                clone.Content.Headers.TryAddWithoutValidation(header.Key, header.Value);
            }
        }

        return clone;
    }
}
