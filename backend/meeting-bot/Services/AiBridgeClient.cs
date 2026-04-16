using System.Text;
using System.Text.Json;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class AiBridgeClient
{
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

        var client = _httpClientFactory.CreateClient(nameof(AiBridgeClient));
        client.Timeout = TimeSpan.FromSeconds(Math.Max(5, _options.TimeoutSeconds));
        using var response = await client.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning("AI bridge fixed line request failed with status {StatusCode}", response.StatusCode);
            return null;
        }

        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        using var json = JsonDocument.Parse(body);
        return json.RootElement.TryGetProperty("audio_uri", out var value) ? value.GetString() : null;
    }
}
