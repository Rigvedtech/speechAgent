using System.Net.Http.Headers;

namespace MeetingBot.Services.Comms;

internal static class GraphCallbackHttpHelper
{
    public static async Task<HttpRequestMessage> ToHttpRequestMessageAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        var uri = new Uri($"{request.Scheme}://{request.Host}{request.PathBase}{request.Path}{request.QueryString}");
        var message = new HttpRequestMessage(new HttpMethod(request.Method), uri);

        foreach (var header in request.Headers)
        {
            if (header.Key.StartsWith(":", StringComparison.Ordinal))
            {
                continue;
            }

            if (header.Key.Equals("Host", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            _ = message.Headers.TryAddWithoutValidation(header.Key, header.Value.AsEnumerable());
        }

        request.EnableBuffering();
        request.Body.Position = 0;
        var body = new MemoryStream();
        await request.Body.CopyToAsync(body, cancellationToken).ConfigureAwait(false);
        body.Position = 0;
        message.Content = new StreamContent(body);
        if (!string.IsNullOrEmpty(request.ContentType))
        {
            message.Content.Headers.ContentType = MediaTypeHeaderValue.Parse(request.ContentType);
        }

        return message;
    }

    public static async Task WriteResponseAsync(HttpResponse response, HttpResponseMessage message, CancellationToken cancellationToken)
    {
        response.StatusCode = (int)message.StatusCode;
        foreach (var h in message.Headers)
        {
            response.Headers[h.Key] = h.Value.ToArray();
        }

        if (message.Content is not null)
        {
            foreach (var h in message.Content.Headers)
            {
                response.Headers[h.Key] = h.Value.ToArray();
            }

            await message.Content.CopyToAsync(response.Body, cancellationToken).ConfigureAwait(false);
        }
    }
}
