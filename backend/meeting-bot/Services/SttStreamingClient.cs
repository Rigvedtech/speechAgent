using System.Buffers;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace MeetingBot.Services;

public sealed class SttStreamingClient : IAsyncDisposable
{
    private readonly Uri _uri;
    private ClientWebSocket? _ws;
    private readonly MemoryStream _textAssembly = new();

    public SttStreamingClient(string wsUrl)
    {
        _uri = new Uri(wsUrl);
    }

    public async Task ConnectAndHandshakeAsync(CancellationToken cancellationToken)
    {
        _ws = new ClientWebSocket();
        // Default pings can overlap heavy PCM sends; STT server must always read the socket anyway.
        _ws.Options.KeepAliveInterval = Timeout.InfiniteTimeSpan;
        await _ws.ConnectAsync(_uri, cancellationToken);

        var first = await ReceiveTextFrameAsync(cancellationToken);
        if (first is null)
        {
            throw new InvalidOperationException("STT websocket closed before handshake.");
        }

        using var doc = JsonDocument.Parse(first);
        var type = doc.RootElement.TryGetProperty("type", out var t) ? t.GetString() : null;
        if (string.Equals(type, "error", StringComparison.OrdinalIgnoreCase))
        {
            var msg = doc.RootElement.TryGetProperty("message", out var m) ? m.GetString() : "Unknown STT error";
            throw new InvalidOperationException($"STT server error: {msg}");
        }

        if (!string.Equals(type, "ready", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"Unexpected STT first message: {first}");
        }
    }

    public async Task SendPcmChunkAsync(ReadOnlyMemory<byte> pcm16le, CancellationToken cancellationToken)
    {
        if (_ws is null)
        {
            throw new InvalidOperationException("STT websocket is not connected.");
        }

        await _ws.SendAsync(pcm16le, WebSocketMessageType.Binary, true, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Receives the next complete text JSON message (handles fragmentation).</summary>
    public async Task<string?> ReceiveTextFrameAsync(CancellationToken cancellationToken)
    {
        if (_ws is null)
        {
            throw new InvalidOperationException("STT websocket is not connected.");
        }

        var buffer = ArrayPool<byte>.Shared.Rent(16384);
        try
        {
            while (true)
            {
                var segment = new ArraySegment<byte>(buffer);
                var result = await _ws.ReceiveAsync(segment, cancellationToken).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    return null;
                }

                if (result.MessageType == WebSocketMessageType.Binary)
                {
                    continue;
                }

                _textAssembly.Write(buffer, 0, result.Count);
                if (result.EndOfMessage)
                {
                    var text = Encoding.UTF8.GetString(_textAssembly.ToArray());
                    _textAssembly.SetLength(0);
                    return text;
                }
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }

    /// <summary>Runs until cancelled or websocket closes. Invokes onFinal for each message with type \"final\".</summary>
    public async Task RunReceiveFinalsLoopAsync(Func<string, Task> onFinal, CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            string? json;
            try
            {
                json = await ReceiveTextFrameAsync(cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return;
            }

            if (json is null)
            {
                return;
            }

            try
            {
                using var doc = JsonDocument.Parse(json);
                if (!doc.RootElement.TryGetProperty("type", out var typeEl))
                {
                    continue;
                }

                var type = typeEl.GetString() ?? string.Empty;
                if (type.Equals("final", StringComparison.OrdinalIgnoreCase) &&
                    doc.RootElement.TryGetProperty("text", out var textEl))
                {
                    var text = textEl.GetString();
                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        await onFinal(text).ConfigureAwait(false);
                    }
                }
            }
            catch (JsonException)
            {
                continue;
            }
        }
    }

    public async Task SendFlushAsync(CancellationToken cancellationToken)
    {
        if (_ws is null || _ws.State != WebSocketState.Open)
        {
            return;
        }

        var bytes = Encoding.UTF8.GetBytes("{\"type\":\"flush\"}");
        await _ws.SendAsync(bytes, WebSocketMessageType.Text, true, cancellationToken).ConfigureAwait(false);
    }

    public async Task SendCloseAsync(CancellationToken cancellationToken)
    {
        if (_ws is null || _ws.State != WebSocketState.Open)
        {
            return;
        }

        var bytes = Encoding.UTF8.GetBytes("{\"type\":\"close\"}");
        try
        {
            await _ws.SendAsync(bytes, WebSocketMessageType.Text, true, cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            // best-effort
        }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_ws is { State: WebSocketState.Open })
            {
                await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "dispose", CancellationToken.None).ConfigureAwait(false);
            }
        }
        catch
        {
            // best-effort
        }

        _ws?.Dispose();
        _ws = null;
        await _textAssembly.DisposeAsync().ConfigureAwait(false);
    }
}
