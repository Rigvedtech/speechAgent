using System.Collections.Concurrent;
using MeetingBot.Models.Domain;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;
using NAudio.CoreAudioApi;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace MeetingBot.Services;

/// <summary>
/// Windows-only: captures loopback (meeting audio through speakers) or microphone, streams PCM16 mono 16kHz to stt_server,
/// and dispatches finals to <see cref="CallLifecycleService.HandleFinalTranscriptAsync"/>.
/// </summary>
public sealed class WindowsSttVoiceLoopStarter : ISttVoiceLoopStarter
{
    private readonly MeetingBotOptions _options;
    private readonly RoomSessionStore _store;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<WindowsSttVoiceLoopStarter> _logger;

    private readonly ConcurrentDictionary<string, CancellationTokenSource> _loops = new(StringComparer.OrdinalIgnoreCase);

    public WindowsSttVoiceLoopStarter(
        IOptions<MeetingBotOptions> options,
        RoomSessionStore store,
        IServiceScopeFactory scopeFactory,
        ILogger<WindowsSttVoiceLoopStarter> logger)
    {
        _options = options.Value;
        _store = store;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public void RequestStartAfterGreeting(string roomId)
    {
        if (!_options.EnableSttVoiceLoop)
        {
            return;
        }

        if (string.Equals(_options.SttLocalAudioSource.Trim(), "None", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        var cts = new CancellationTokenSource();
        if (!_loops.TryAdd(roomId, cts))
        {
            cts.Dispose();
            return;
        }

        _ = Task.Run(() => RunVoiceLoopSafeAsync(roomId, cts), cts.Token);
    }

    public Task StopAsync(string roomId, CancellationToken cancellationToken = default)
    {
        if (_loops.TryGetValue(roomId, out var cts))
        {
            try
            {
                cts.Cancel();
            }
            catch
            {
                // ignore
            }
        }

        return Task.CompletedTask;
    }

    private async Task RunVoiceLoopSafeAsync(string roomId, CancellationTokenSource outerCts)
    {
        try
        {
            await RunVoiceLoopAsync(roomId, outerCts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            AppendEvent(roomId, "stt-voice-loop-stopped", "cancelled");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "STT voice loop failed for room {RoomId}", roomId);
            AppendEvent(roomId, "stt-voice-loop-failed", ex.Message);
        }
        finally
        {
            if (_loops.TryRemove(roomId, out var left))
            {
                left.Dispose();
            }
        }
    }

    private async Task RunVoiceLoopAsync(string roomId, CancellationToken cancellationToken)
    {
        AppendEvent(roomId, "stt-voice-loop-starting", $"source={_options.SttLocalAudioSource}; ws={_options.SttWebSocketUrl}");

        await using var stt = new SttStreamingClient(_options.SttWebSocketUrl);
        await stt.ConnectAndHandshakeAsync(cancellationToken).ConfigureAwait(false);
        AppendEvent(roomId, "stt-voice-loop-stt-ready", "connected");

        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var token = linked.Token;

        var receiveTask = stt.RunReceiveFinalsLoopAsync(
            text => OnFinalTranscriptAsync(roomId, text, CancellationToken.None),
            token);

        Task pumpTask;
        if (string.Equals(_options.SttLocalAudioSource, "Mic", StringComparison.OrdinalIgnoreCase))
        {
            pumpTask = PumpMicrophoneToSttAsync(stt, token);
        }
        else
        {
            pumpTask = PumpLoopbackToSttAsync(stt, token);
        }

        try
        {
            var finished = await Task.WhenAny(receiveTask, pumpTask).ConfigureAwait(false);
            if (finished.IsFaulted)
            {
                await finished.ConfigureAwait(false);
            }

            if (finished == receiveTask)
            {
                _logger.LogInformation(
                    "STT voice loop for room {RoomId}: receive task finished first (server closed WS, cancelled, or idle).",
                    roomId);
            }
            else
            {
                _logger.LogInformation(
                    "STT voice loop for room {RoomId}: audio pump finished first (usually cancellation when the call ends).",
                    roomId);
            }
        }
        finally
        {
            linked.Cancel();
            try
            {
                await stt.SendFlushAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }

            try
            {
                await stt.SendCloseAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }

            try
            {
                await receiveTask.WaitAsync(TimeSpan.FromSeconds(3), CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }

            try
            {
                await pumpTask.WaitAsync(TimeSpan.FromSeconds(3), CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // ignore
            }
        }

        AppendEvent(roomId, "stt-voice-loop-ended", "complete");
    }

    private async Task OnFinalTranscriptAsync(string roomId, string transcript, CancellationToken cancellationToken)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var lifecycle = scope.ServiceProvider.GetRequiredService<CallLifecycleService>();
        await lifecycle.TryConsumeSttFinalAsync(roomId, transcript, cancellationToken).ConfigureAwait(false);
    }

    private async Task PumpLoopbackToSttAsync(SttStreamingClient stt, CancellationToken cancellationToken)
    {
        using var capture = CreateLoopbackCapture(out var captureDeviceName, out var routingNote);
        _logger.LogInformation(
            "STT loopback: capturing Windows playback mix from {Device}. SampleRate={Rate}Hz Channels={Ch}. {RoutingNote} " +
            "Remote speech appears only if Teams desktop on THIS PC is in the same call and meeting audio plays on that device. " +
            "Guests on phones/other PCs are not in this mix. Use app-hosted media for that, or SttLocalAudioSource=Mic to test with your microphone.",
            captureDeviceName,
            capture.WaveFormat.SampleRate,
            capture.WaveFormat.Channels,
            routingNote);

        var buffer = new BufferedWaveProvider(capture.WaveFormat)
        {
            DiscardOnBufferOverflow = true,
            BufferLength = 1024 * 1024
        };

        capture.DataAvailable += (_, e) =>
        {
            buffer.AddSamples(e.Buffer, 0, e.BytesRecorded);
        };

        capture.StartRecording();
        try
        {
            await PumpResampledPcmAsync(buffer, stt, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            capture.StopRecording();
        }
    }

    private static WasapiLoopbackCapture CreateLoopbackCapture(out string captureDeviceName, out string routingNote)
    {
        captureDeviceName = string.Empty;
        routingNote = string.Empty;
        var enumerator = new MMDeviceEnumerator();
        try
        {
            var comms = TryGetDefaultRender(enumerator, Role.Communications);
            var media = TryGetDefaultRender(enumerator, Role.Multimedia);

            MMDevice? chosen = null;
            if (comms is not null && media is not null &&
                !string.Equals(comms.ID, media.ID, StringComparison.OrdinalIgnoreCase))
            {
                chosen = comms;
                routingNote =
                    "Communications default render differs from multimedia; using communications (Teams often routes meeting audio here).";
            }
            else if (comms is not null)
            {
                chosen = comms;
                routingNote = media is null
                    ? "Using communications default render (multimedia default unavailable for comparison)."
                    : "Communications and multimedia default render are the same device.";
            }
            else if (media is not null)
            {
                chosen = media;
                routingNote = "Using multimedia default render (communications default unavailable).";
            }

            if (chosen is not null)
            {
                captureDeviceName = chosen.FriendlyName;
                return new WasapiLoopbackCapture(chosen);
            }

            routingNote =
                "Using NAudio default loopback (no explicit default render device). If capture is silent, check Windows sound defaults.";
            var fallback = new WasapiLoopbackCapture();
            captureDeviceName = TryGetDefaultRender(enumerator, Role.Multimedia)?.FriendlyName
                ?? TryGetDefaultRender(enumerator, Role.Communications)?.FriendlyName
                ?? "(unknown loopback device)";
            return fallback;
        }
        finally
        {
            enumerator.Dispose();
        }
    }

    private static MMDevice? TryGetDefaultRender(MMDeviceEnumerator enumerator, Role role)
    {
        try
        {
            return enumerator.GetDefaultAudioEndpoint(DataFlow.Render, role);
        }
        catch
        {
            return null;
        }
    }

    private async Task PumpMicrophoneToSttAsync(SttStreamingClient stt, CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "STT mic: capturing default recording device at 44100Hz mono. Speak into the PC mic to test; remote Teams users are NOT heard unless their audio plays on this machine.");

        using var waveIn = new WaveInEvent
        {
            WaveFormat = new WaveFormat(44100, 16, 1),
            BufferMilliseconds = 50
        };

        var buffer = new BufferedWaveProvider(waveIn.WaveFormat)
        {
            DiscardOnBufferOverflow = true,
            BufferLength = 1024 * 1024
        };

        waveIn.DataAvailable += (_, e) =>
        {
            buffer.AddSamples(e.Buffer, 0, e.BytesRecorded);
        };

        waveIn.StartRecording();
        try
        {
            await PumpResampledPcmAsync(buffer, stt, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            waveIn.StopRecording();
        }
    }

    private static async Task PumpResampledPcmAsync(IWaveProvider source, SttStreamingClient stt, CancellationToken cancellationToken)
    {
        var sample = source.ToSampleProvider();
        if (sample.WaveFormat.Channels > 1)
        {
            sample = new StereoToMonoSampleProvider(sample)
            {
                LeftVolume = 0.5f,
                RightVolume = 0.5f
            };
        }

        var resampled = new WdlResamplingSampleProvider(sample, 16000);
        var wave16 = new SampleToWaveProvider16(resampled);
        var frame = new byte[640];

        while (!cancellationToken.IsCancellationRequested)
        {
            var read = wave16.Read(frame, 0, frame.Length);
            if (read > 0)
            {
                await stt.SendPcmChunkAsync(frame.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await Task.Delay(5, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private void AppendEvent(string roomId, string eventType, string details)
    {
        if (!_store.TryGet(roomId, out var session) || session is null)
        {
            return;
        }

        session.Events.Add(new CallEvent { EventType = eventType, Details = details });
        _store.Upsert(session);
    }
}
