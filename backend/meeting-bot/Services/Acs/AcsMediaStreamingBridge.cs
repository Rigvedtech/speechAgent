using System.Net.WebSockets;
using System.Text;
using Azure.Communication.CallAutomation;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services.Acs;

/// <summary>Receives ACS mixed audio over WebSocket and forwards PCM to STT; handles one ACS media connection.</summary>
public sealed class AcsMediaStreamingBridge
{
    private readonly AcsCallRegistry _registry;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly MeetingBotOptions _options;
    private readonly ILogger<AcsMediaStreamingBridge> _logger;

    public AcsMediaStreamingBridge(
        AcsCallRegistry registry,
        IServiceScopeFactory scopeFactory,
        IOptions<MeetingBotOptions> options,
        ILogger<AcsMediaStreamingBridge> logger)
    {
        _registry = registry;
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;
    }

    public async Task HandleConnectionAsync(WebSocket webSocket, string? callConnectionId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(callConnectionId))
        {
            _logger.LogWarning("ACS media WebSocket missing x-ms-call-connection-id header.");
            await webSocket.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Missing call connection id", cancellationToken)
                .ConfigureAwait(false);
            return;
        }

        if (!_registry.TryGetRoomId(callConnectionId, out var roomId) || string.IsNullOrWhiteSpace(roomId))
        {
            _logger.LogWarning("ACS media WebSocket for unknown call {CallId}", callConnectionId);
            await webSocket.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Unknown call", cancellationToken)
                .ConfigureAwait(false);
            return;
        }

        _logger.LogInformation("ACS media stream connected. Call={CallId} Room={RoomId}", callConnectionId, roomId);

        await using var stt = new SttStreamingClient(_options.SttWebSocketUrl);
        await stt.ConnectAndHandshakeAsync(cancellationToken).ConfigureAwait(false);

        var sttReceive = stt.RunReceiveFinalsLoopAsync(
            async text =>
            {
                await using var scope = _scopeFactory.CreateAsyncScope();
                var lifecycle = scope.ServiceProvider.GetRequiredService<CallLifecycleService>();
                await lifecycle.TryConsumeSttFinalAsync(roomId, text, CancellationToken.None).ConfigureAwait(false);
            },
            cancellationToken);

        try
        {
            var buffer = new byte[32 * 1024];
            while (webSocket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var result = await webSocket.ReceiveAsync(buffer, cancellationToken).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    break;
                }

                if (result.MessageType != WebSocketMessageType.Text)
                {
                    continue;
                }

                var json = Encoding.UTF8.GetString(buffer, 0, result.Count);
                if (!result.EndOfMessage)
                {
                    _logger.LogDebug("Skipping fragmented ACS media text frame (length={Len})", result.Count);
                    continue;
                }

                StreamingData parsed;
                try
                {
                    parsed = StreamingData.Parse(json);
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "Non-audio ACS media frame: {Preview}", json.Length > 120 ? json[..120] : json);
                    continue;
                }

                if (parsed is not AudioData audioData || audioData.Data.IsEmpty)
                {
                    continue;
                }

                if (audioData.IsSilent)
                {
                    continue;
                }

                await stt.SendPcmChunkAsync(audioData.Data, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            try
            {
                await sttReceive.ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                // expected on shutdown
            }

            if (webSocket.State == WebSocketState.Open || webSocket.State == WebSocketState.CloseReceived)
            {
                await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "done", CancellationToken.None)
                    .ConfigureAwait(false);
            }
        }

        _logger.LogInformation("ACS media stream ended. Call={CallId} Room={RoomId}", callConnectionId, roomId);
    }
}
