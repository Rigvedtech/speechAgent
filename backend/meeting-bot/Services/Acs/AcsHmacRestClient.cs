using System.Globalization;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;

namespace MeetingBot.Services.Acs;

/// <summary>POST JSON to ACS data-plane APIs with HMAC-SHA256 signing (connection string access key).</summary>
internal static class AcsHmacRestClient
{
    private static readonly HttpClient Http = new();

    public static async Task<(int Status, string Body)> PostJsonAsync(
        string connectionString,
        string pathAndQuery,
        string jsonBody,
        CancellationToken cancellationToken)
    {
        var (endpoint, accessKey) = AcsConnectionString.Parse(connectionString);
        var requestUri = new Uri($"{endpoint.AbsoluteUri.TrimEnd('/')}{pathAndQuery}");

        var contentBytes = Encoding.UTF8.GetBytes(jsonBody);
        var contentHash = Convert.ToBase64String(SHA256.HashData(contentBytes));
        var date = DateTimeOffset.UtcNow.ToString("r", CultureInfo.InvariantCulture);
        var host = requestUri.Authority;
        var stringToSign = $"POST\n{requestUri.PathAndQuery}\n{date};{host};{contentHash}";
        var signature = Convert.ToBase64String(
            HMACSHA256.HashData(Convert.FromBase64String(accessKey), Encoding.UTF8.GetBytes(stringToSign)));

        using var request = new HttpRequestMessage(HttpMethod.Post, requestUri);
        request.Content = new ByteArrayContent(contentBytes);
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        request.Headers.Add("x-ms-date", date);
        request.Headers.Add("x-ms-content-sha256", contentHash);
        request.Headers.TryAddWithoutValidation(
            "Authorization",
            $"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={signature}");

        using var response = await Http.SendAsync(request, cancellationToken).ConfigureAwait(false);
        var body = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        return ((int)response.StatusCode, body);
    }
}
