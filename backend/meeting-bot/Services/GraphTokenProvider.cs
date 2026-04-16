using System.Net.Http.Headers;
using System.Text.Json;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class GraphTokenProvider
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly GraphOptions _options;
    private string _cachedToken = string.Empty;
    private DateTimeOffset _expiresAt = DateTimeOffset.MinValue;

    public GraphTokenProvider(IHttpClientFactory httpClientFactory, IOptions<GraphOptions> options)
    {
        _httpClientFactory = httpClientFactory;
        _options = options.Value;
    }

    public async Task<string> GetAccessTokenAsync(CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(_cachedToken) && _expiresAt > DateTimeOffset.UtcNow.AddMinutes(2))
        {
            return _cachedToken;
        }

        var tokenUrl = $"https://login.microsoftonline.com/{_options.TenantId}/oauth2/v2.0/token";
        using var request = new HttpRequestMessage(HttpMethod.Post, tokenUrl)
        {
            Content = new FormUrlEncodedContent(
                new Dictionary<string, string>
                {
                    ["client_id"] = _options.ClientId,
                    ["client_secret"] = _options.ClientSecret,
                    ["scope"] = _options.Scope,
                    ["grant_type"] = "client_credentials"
                })
        };

        var client = _httpClientFactory.CreateClient(nameof(GraphTokenProvider));
        using var response = await client.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();

        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var json = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
        _cachedToken = json.RootElement.GetProperty("access_token").GetString() ?? string.Empty;
        var expiresIn = json.RootElement.GetProperty("expires_in").GetInt32();
        _expiresAt = DateTimeOffset.UtcNow.AddSeconds(expiresIn);
        return _cachedToken;
    }

    public async Task<HttpRequestMessage> CreateGraphRequestAsync(HttpMethod method, string uri, CancellationToken cancellationToken)
    {
        var token = await GetAccessTokenAsync(cancellationToken);
        var request = new HttpRequestMessage(method, $"https://graph.microsoft.com/v1.0{uri}");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }
}
