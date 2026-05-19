using System.Runtime.InteropServices;
using MeetingBot.Models.Options;
using MeetingBot.Services;
using Microsoft.Extensions.Options;
using Microsoft.Graph.Communications.Calls.Media;
using Microsoft.Skype.Bots.Media;

namespace MeetingBot.Services.Comms;

/// <summary>Streams Teams mixed audio (PCM16K) from an <see cref="IAudioSocket"/> into <see cref="SttStreamingClient"/>.</summary>
internal sealed class InCallSttBridge : IAsyncDisposable
{
    private readonly string _roomId;
    private readonly IAudioSocket _audioSocket;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly MeetingBotOptions _options;
    private readonly ILogger<InCallSttBridge> _logger;
    private readonly CancellationTokenSource _cts = new();
    private SttStreamingClient? _stt;
    private Task? _receiveLoop;

    public InCallSttBridge(
        string roomId,
        ILocalMediaSession mediaSession,
        IOptions<MeetingBotOptions> options,
        IServiceScopeFactory scopeFactory,
        ILogger<InCallSttBridge> logger)
    {
        _roomId = roomId;
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;
        _audioSocket = mediaSession.AudioSocket ?? throw new InvalidOperationException("Media session has no audio socket.");
        _audioSocket.AudioMediaReceived += OnAudioMediaReceived;
        _ = StartSttBackgroundAsync();
    }

    private async Task StartSttBackgroundAsync()
    {
        try
        {
            var stt = new SttStreamingClient(_options.SttWebSocketUrl);
            await stt.ConnectAndHandshakeAsync(_cts.Token).ConfigureAwait(false);
            _stt = stt;
            _receiveLoop = stt.RunReceiveFinalsLoopAsync(
                async text =>
                {
                    await using var scope = _scopeFactory.CreateAsyncScope();
                    var lifecycle = scope.ServiceProvider.GetRequiredService<CallLifecycleService>();
                    await lifecycle.TryConsumeSttFinalAsync(_roomId, text, CancellationToken.None).ConfigureAwait(false);
                },
                _cts.Token);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "In-call STT websocket failed to start for room {RoomId}", _roomId);
        }
    }

    private void OnAudioMediaReceived(object? sender, AudioMediaReceivedEventArgs e)
    {
        try
        {
            var stt = _stt;
            if (stt is null || e.Buffer.Length <= 0)
            {
                return;
            }

            var len = (int)e.Buffer.Length;
            var bytes = new byte[len];
            Marshal.Copy(e.Buffer.Data, bytes, 0, len);

            // Typical stereo 16 kHz 20 ms frame is 1280 bytes; STT expects mono PCM16LE.
            if (len >= 1280 && len % 1280 == 0)
            {
                var stereoSamples = len / 4;
                var mono = new byte[stereoSamples * 2];
                for (var i = 0; i < stereoSamples; i++)
                {
                    var lo = BitConverter.ToInt16(bytes, i * 4);
                    var ro = BitConverter.ToInt16(bytes, i * 4 + 2);
                    var m = (short)(((int)lo + (int)ro) / 2);
                    BitConverter.GetBytes(m).CopyTo(mono, i * 2);
                }

                bytes = mono;
            }

            _ = stt.SendPcmChunkAsync(bytes, CancellationToken.None);
        }
        catch (Exception ex)
        {
            _logger.LogTrace(ex, "In-call STT audio chunk send failed (call may be ending).");
        }
        finally
        {
            e.Buffer.Dispose();
        }
    }

    public async ValueTask DisposeAsync()
    {
        _audioSocket.AudioMediaReceived -= OnAudioMediaReceived;
        try
        {
            _cts.Cancel();
        }
        catch
        {
            // ignore
        }

        if (_receiveLoop is not null)
        {
            try
            {
                await _receiveLoop.WaitAsync(TimeSpan.FromSeconds(3), CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }
        }

        if (_stt is not null)
        {
            try
            {
                await _stt.SendFlushAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }

            try
            {
                await _stt.SendCloseAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }

            await _stt.DisposeAsync().ConfigureAwait(false);
            _stt = null;
        }

        _cts.Dispose();
    }
}
