using System.Collections.Concurrent;
using System.Linq;
using System.Net;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using Microsoft.Graph.Communications.Calls;
using Microsoft.Graph.Communications.Calls.Media;
using Microsoft.Graph.Communications.Client;
using Microsoft.Graph.Communications.Common.Telemetry;
using Microsoft.Graph.Models;
using Microsoft.Skype.Bots.Media;
namespace MeetingBot.Services.Comms;

/// <summary>Hosts the Graph Communications Calling client for application-hosted media join + notification processing.</summary>
public sealed class TeamsCommunicationsService : IHostedService, IDisposable
{
    private readonly IOptions<MeetingBotOptions> _meetingOptions;
    private readonly IOptions<MediaPlatformOptions> _mediaOptions;
    private readonly IOptions<GraphOptions> _graphOptions;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILoggerFactory _loggerFactory;
    private readonly ILogger<TeamsCommunicationsService> _logger;
    private ICommunicationsClient? _client;
    private GraphLogger? _graphLogger;
    private readonly ConcurrentDictionary<string, InCallSttBridge> _bridgesByCallId = new(StringComparer.OrdinalIgnoreCase);

    public TeamsCommunicationsService(
        IOptions<MeetingBotOptions> meetingOptions,
        IOptions<MediaPlatformOptions> mediaOptions,
        IOptions<GraphOptions> graphOptions,
        IServiceScopeFactory scopeFactory,
        ILoggerFactory loggerFactory,
        ILogger<TeamsCommunicationsService> logger)
    {
        _meetingOptions = meetingOptions;
        _mediaOptions = mediaOptions;
        _graphOptions = graphOptions;
        _scopeFactory = scopeFactory;
        _loggerFactory = loggerFactory;
        _logger = logger;
    }

    public bool IsEnabled => _client is not null;

    public Task StartAsync(CancellationToken cancellationToken)
    {
        TryInitialize();
        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        Dispose();
        return Task.CompletedTask;
    }

    private void TryInitialize()
    {
        var mb = _meetingOptions.Value;
        var mp = _mediaOptions.Value;
        var g = _graphOptions.Value;

        if (!mb.UseApplicationHostedMedia)
        {
            _logger.LogInformation("Application-hosted media is disabled (MeetingBot:UseApplicationHostedMedia=false). Using HTTP Graph join + local loopback STT.");
            return;
        }

        if (!mp.IsComplete())
        {
            _logger.LogWarning(
                "UseApplicationHostedMedia is true but MediaPlatform configuration is incomplete. " +
                "Set MediaPlatform:CertificateThumbprint, InstanceInternalPort, InstancePublicPort, InstancePublicIPAddress, ServiceFqdn.");
            return;
        }

        if (string.IsNullOrWhiteSpace(g.ClientId) || string.IsNullOrWhiteSpace(g.ClientSecret))
        {
            _logger.LogWarning("Graph ClientId/ClientSecret missing; cannot start Communications client.");
            return;
        }

        try
        {
            _graphLogger = new GraphLogger("MeetingBot");
            var auth = new CommsAuthenticationProvider("MeetingBot", g.ClientId.Trim(), g.ClientSecret.Trim(), _graphLogger);

            var builder = new CommunicationsClientBuilder("MeetingBot", g.ClientId.Trim(), _graphLogger)
                .SetAuthenticationProvider(auth)
                .SetNotificationUrl(BuildNotificationUri(mb))
                .SetMediaPlatformSettings(BuildMediaPlatformSettings(mp, g))
                .SetServiceBaseUrl(new Uri(mb.PlaceCallEndpointUrl.Trim()));

            _client = builder.Build();
            _client.Calls().OnUpdated += OnCallsCollectionUpdated;
            _logger.LogInformation(
                "Graph Communications client initialized (app-hosted media). NotificationUrl={Notification}; MediaFqdn={Fqdn}; PublicPort={Port}",
                BuildNotificationUri(mb),
                mp.ServiceFqdn.Trim(),
                mp.InstancePublicPort);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to initialize Graph Communications client; falling back is not automatic—disable UseApplicationHostedMedia or fix media config.");
            _client?.Dispose();
            _client = null;
            _graphLogger?.Dispose();
            _graphLogger = null;
        }
    }

    private static Uri BuildNotificationUri(MeetingBotOptions mb)
    {
        var baseUrl = mb.CallbackBaseUrl.TrimEnd('/');
        return new Uri($"{baseUrl}/api/calls/callback");
    }

    private static MediaPlatformSettings BuildMediaPlatformSettings(MediaPlatformOptions mp, GraphOptions g)
    {
        if (!IPAddress.TryParse(mp.InstancePublicIPAddress.Trim(), out var ip))
        {
            throw new InvalidOperationException($"MediaPlatform:InstancePublicIPAddress is not a valid IP address: '{mp.InstancePublicIPAddress}'.");
        }

        return new MediaPlatformSettings
        {
            ApplicationId = g.ClientId.Trim(),
            MediaPlatformInstanceSettings = new MediaPlatformInstanceSettings
            {
                CertificateThumbprint = mp.CertificateThumbprint.Trim(),
                InstanceInternalPort = mp.InstanceInternalPort,
                InstancePublicIPAddress = ip,
                InstancePublicPort = mp.InstancePublicPort,
                ServiceFqdn = mp.ServiceFqdn.Trim(),
            },
        };
    }

    private void OnCallsCollectionUpdated(ICallCollection sender, object args)
    {
        dynamic a = args;
        foreach (ICall removed in a.RemovedResources)
        {
            if (_bridgesByCallId.TryRemove(removed.Id, out var bridge))
            {
                bridge.DisposeAsync().GetAwaiter().GetResult();
            }
        }
    }

    public async Task<HttpResponseMessage?> ProcessIncomingNotificationAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        if (_client is null)
        {
            return null;
        }

        using var httpMessage = await GraphCallbackHttpHelper.ToHttpRequestMessageAsync(request, cancellationToken).ConfigureAwait(false);
        return await _client.ProcessNotificationAsync(httpMessage).ConfigureAwait(false);
    }

    public async Task<string> JoinMeetingAsync(string roomId, string joinUrl, CancellationToken cancellationToken)
    {
        if (_client is null)
        {
            throw new InvalidOperationException("Communications client is not initialized.");
        }

        var mb = _meetingOptions.Value;
        var (chatInfo, meetingInfo, tenantId) = TeamsJoinInfoParser.Parse(joinUrl);
        var mediaSession = _client.CreateMediaSession(
            new AudioSocketSettings
            {
                StreamDirections = StreamDirection.Recvonly,
                SupportedAudioFormat = AudioFormat.Pcm16K,
            });

        var bridgeLogger = _loggerFactory.CreateLogger<InCallSttBridge>();
        var bridge = new InCallSttBridge(roomId, mediaSession, _meetingOptions, _scopeFactory, bridgeLogger);

        var joinParams = new JoinMeetingParameters(chatInfo, meetingInfo, mediaSession)
        {
            TenantId = tenantId,
        };

        var scenarioId = Guid.NewGuid();
        var call = await _client.Calls().AddAsync(joinParams, scenarioId).ConfigureAwait(false);

        _bridgesByCallId[call.Id] = bridge;

        call.OnUpdated += async (_, e) =>
        {
            if (e.NewResource.State != CallState.Established)
            {
                return;
            }

            if (e.OldResource?.State == CallState.Established)
            {
                return;
            }

            try
            {
                await using var scope = _scopeFactory.CreateAsyncScope();
                var lifecycle = scope.ServiceProvider.GetRequiredService<CallLifecycleService>();
                await lifecycle.OnAppHostedCallEstablishedAsync(call.Id, CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "App-hosted call established handler failed for call {CallId}", call.Id);
            }
        };

        _logger.LogInformation("Joined meeting via Communications SDK for room {RoomId}; callId={CallId}", roomId, call.Id);
        return call.Id;
    }

    public async Task TryDeleteCallAsync(string callId, CancellationToken cancellationToken)
    {
        if (_client is null || string.IsNullOrWhiteSpace(callId))
        {
            return;
        }

        try
        {
            var call = _client.Calls()[callId];
            if (call is not null)
            {
                await call.DeleteAsync().ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            _logger.LogInformation(ex, "SDK delete call failed for {CallId}; call may already be gone.", callId);
        }

        _bridgesByCallId.TryRemove(callId, out var removed);
        if (removed is not null)
        {
            await removed.DisposeAsync().ConfigureAwait(false);
        }
    }

    public void Dispose()
    {
        foreach (var key in _bridgesByCallId.Keys.ToArray())
        {
            if (!_bridgesByCallId.TryRemove(key, out var b))
            {
                continue;
            }

            try
            {
                b.DisposeAsync().AsTask().GetAwaiter().GetResult();
            }
            catch
            {
                // ignore
            }
        }

        try
        {
            _client?.Dispose();
        }
        catch
        {
            // ignore
        }

        _client = null;

        try
        {
            _graphLogger?.Dispose();
        }
        catch
        {
            // ignore
        }

        _graphLogger = null;
    }
}
