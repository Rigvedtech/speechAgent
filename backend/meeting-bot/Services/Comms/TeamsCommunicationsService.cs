using System.Collections.Concurrent;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Security.Cryptography.X509Certificates;
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

/// <summary>Forwards GraphLogger internal SDK log events to ILogger.</summary>
file sealed class GraphLogForwarder : IObserver<LogEvent>, IDisposable
{
    private readonly ILogger _logger;
    private IDisposable? _subscription;

    public GraphLogForwarder(ILogger logger, GraphLogger graphLogger)
    {
        _logger = logger;
        _subscription = graphLogger.Subscribe(this);
    }

    public void OnNext(LogEvent value)
    {
        var level = value.Level switch
        {
            TraceLevel.Error => Microsoft.Extensions.Logging.LogLevel.Error,
            TraceLevel.Warning => Microsoft.Extensions.Logging.LogLevel.Warning,
            _ => Microsoft.Extensions.Logging.LogLevel.Information,
        };
        _logger.Log(level, "[SDK:{Component}] {Message}", value.Component, value.Message);
    }

    public void OnError(Exception error) => _logger.LogError(error, "[SDK] Observer error");
    public void OnCompleted() { }

    public void Dispose()
    {
        _subscription?.Dispose();
        _subscription = null;
    }
}

/// <summary>Forwards IMediaPlatformLogger (Skype.Bots.Media) calls to ILogger.</summary>
file sealed class MediaPlatformLogForwarder : IMediaPlatformLogger
{
    private readonly ILogger _logger;
    public MediaPlatformLogForwarder(ILogger logger) => _logger = logger;

    public void WriteLog(Microsoft.Skype.Bots.Media.LogLevel level, string message)
    {
        var netLevel = level switch
        {
            Microsoft.Skype.Bots.Media.LogLevel.Error => Microsoft.Extensions.Logging.LogLevel.Error,
            Microsoft.Skype.Bots.Media.LogLevel.Warning => Microsoft.Extensions.Logging.LogLevel.Warning,
            _ => Microsoft.Extensions.Logging.LogLevel.Information,
        };
        _logger.Log(netLevel, "[MEDIA] {Message}", message);
    }
}

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
    private IDisposable? _graphLogForwarder;
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

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        await DisposeInternalAsync(cancellationToken).ConfigureAwait(false);
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
            VerifyCertificateInStore(mp.CertificateThumbprint.Trim());

            _graphLogger = new GraphLogger("MeetingBot");
            _graphLogger.DiagnosticLevel = TraceLevel.Verbose;
            _graphLogForwarder = new GraphLogForwarder(_logger, _graphLogger);

            var auth = new CommsAuthenticationProvider("MeetingBot", g.ClientId.Trim(), g.ClientSecret.Trim(), _graphLogger);

            var builder = new CommunicationsClientBuilder("MeetingBot", g.ClientId.Trim(), _graphLogger)
                .SetAuthenticationProvider(auth)
                .SetNotificationUrl(BuildNotificationUri(mb))
                .SetMediaPlatformSettings(BuildMediaPlatformSettings(mp, g, _logger))
                .SetServiceBaseUrl(new Uri(mb.PlaceCallEndpointUrl.Trim()));

            _client = builder.Build();
            _client.Calls().OnUpdated += OnCallsCollectionUpdated;
            _logger.LogInformation(
                "Graph Communications client initialized (app-hosted media). NotificationUrl={Notification}; MediaFqdn={Fqdn}; TcpPort={Port}; UdpPortRange={UdpMin}-{UdpMax}",
                BuildNotificationUri(mb),
                mp.ServiceFqdn.Trim(),
                mp.InstancePublicPort,
                mp.MediaPortMin,
                mp.MediaPortMax);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to initialize Graph Communications client; falling back is not automatic—disable UseApplicationHostedMedia or fix media config.");
            _client?.Dispose();
            _client = null;
            _graphLogForwarder?.Dispose();
            _graphLogForwarder = null;
            _graphLogger?.Dispose();
            _graphLogger = null;
        }
    }

    private void VerifyCertificateInStore(string thumbprint)
    {
        using var store = new X509Store(StoreName.My, StoreLocation.LocalMachine);
        store.Open(OpenFlags.ReadOnly);
        var certs = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, validOnly: false);
        if (certs.Count == 0)
        {
            _logger.LogError(
                "CERT CHECK FAILED: Certificate with thumbprint {Thumbprint} NOT found in LocalMachine\\My store. " +
                "Media platform will fail to start. Install the certificate with private key under SYSTEM account.",
                thumbprint);
            return;
        }

        var cert = certs[0];
        _logger.LogInformation(
            "CERT CHECK OK: Found {Subject} (thumbprint={Thumbprint}, expiry={Expiry}, hasPrivateKey={HasKey}) in LocalMachine\\My",
            cert.Subject, thumbprint, cert.NotAfter.ToShortDateString(), cert.HasPrivateKey);

        if (!cert.HasPrivateKey)
        {
            _logger.LogError(
                "CERT CHECK FAILED: Certificate {Subject} was found but has NO private key accessible to this process. " +
                "Grant read access to the private key for the service account.",
                cert.Subject);
        }
    }

    private static Uri BuildNotificationUri(MeetingBotOptions mb)
    {
        var baseUrl = mb.CallbackBaseUrl.TrimEnd('/');
        return new Uri($"{baseUrl}/api/calls/callback");
    }

    private static MediaPlatformSettings BuildMediaPlatformSettings(MediaPlatformOptions mp, GraphOptions g, ILogger logger)
    {
        if (!IPAddress.TryParse(mp.InstancePublicIPAddress.Trim(), out var ip))
        {
            throw new InvalidOperationException($"MediaPlatform:InstancePublicIPAddress is not a valid IP address: '{mp.InstancePublicIPAddress}'.");
        }

        if (mp.MediaPortMin <= 0 || mp.MediaPortMax < mp.MediaPortMin)
        {
            throw new InvalidOperationException(
                $"MediaPlatform: invalid MediaPortMin/MediaPortMax ({mp.MediaPortMin}-{mp.MediaPortMax}). Use e.g. 41000-41999 and open UDP on firewall.");
        }

        return new MediaPlatformSettings
        {
            ApplicationId = g.ClientId.Trim(),
            MediaPlatformLogger = new MediaPlatformLogForwarder(logger),
            MediaPlatformInstanceSettings = new MediaPlatformInstanceSettings
            {
                CertificateThumbprint = mp.CertificateThumbprint.Trim(),
                InstanceInternalPort = mp.InstanceInternalPort,
                InstancePublicIPAddress = ip,
                InstancePublicPort = mp.InstancePublicPort,
                ServiceFqdn = mp.ServiceFqdn.Trim(),
                MediaPortRange = new PortRange((uint)mp.MediaPortMin, (uint)mp.MediaPortMax),
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
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await bridge.DisposeAsync().ConfigureAwait(false);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogDebug(ex, "Bridge dispose failed for removed call {CallId}", removed.Id);
                    }
                });
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
        // Diagnostic: verify this process can bind a raw UDP socket at all
        try
        {
            using var testSock = new System.Net.Sockets.UdpClient();
            testSock.Client.Bind(new System.Net.IPEndPoint(System.Net.IPAddress.Any, 41000));
            _logger.LogInformation("UDP-BIND-TEST: Successfully bound UDP test socket on 0.0.0.0:41000 — OS allows UDP binding.");
        }
        catch (Exception sockEx)
        {
            _logger.LogError(sockEx, "UDP-BIND-TEST FAILED: Cannot bind UDP to port 41000 — {Message}. Check Windows Firewall / netsh port exclusions.", sockEx.Message);
        }

        var mediaSession = _client.CreateMediaSession(
            new AudioSocketSettings
            {
                StreamDirections = StreamDirection.Sendrecv,
                SupportedAudioFormat = AudioFormat.Pcm16K,
            });

        _logger.LogInformation("CreateMediaSession done. SessionId={SessionId}", mediaSession.MediaSessionId);

        var bridgeLogger = _loggerFactory.CreateLogger<InCallSttBridge>();
        var bridge = new InCallSttBridge(roomId, mediaSession, _meetingOptions, _scopeFactory, bridgeLogger);

        var joinParams = new JoinMeetingParameters(chatInfo, meetingInfo, mediaSession)
        {
            TenantId = tenantId,
        };

        var scenarioId = Guid.NewGuid();
        _logger.LogInformation(
            "Calling AddAsync for room {RoomId}; scenarioId={ScenarioId}; MediaFqdn={Fqdn}; PublicIP={IP}; TcpPort={Port}; UdpRange={UdpMin}-{UdpMax}",
            roomId, scenarioId,
            _mediaOptions.Value.ServiceFqdn,
            _mediaOptions.Value.InstancePublicIPAddress,
            _mediaOptions.Value.InstancePublicPort,
            _mediaOptions.Value.MediaPortMin,
            _mediaOptions.Value.MediaPortMax);

        ICall call;
        try
        {
            call = await _client.Calls().AddAsync(joinParams, scenarioId).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "AddAsync FAILED for room {RoomId}. Check: (1) FortiGate UDP policy for 41000-41999 inbound, " +
                "(2) certificate private key accessible, (3) Application Access Policy assigned for organizer. " +
                "Error type={ErrorType} Message={ErrorMessage}",
                roomId, ex.GetType().Name, ex.Message);
            throw;
        }

        _bridgesByCallId[call.Id] = bridge;

        // Background UDP monitor — logs UDP + TCP state every 2 s for 30 s so you can see it in this terminal
        _ = Task.Run(async () =>
        {
            var botPid = System.Diagnostics.Process.GetCurrentProcess().Id;
            for (var i = 0; i < 15; i++)
            {
                await Task.Delay(2000).ConfigureAwait(false);
                try
                {
                    var udpLines = System.Net.NetworkInformation.IPGlobalProperties
                        .GetIPGlobalProperties()
                        .GetActiveUdpListeners()
                        .Where(ep => ep.Port >= 41000 && ep.Port <= 41999)
                        .Select(ep => ep.ToString())
                        .ToArray();

                    var tcpLines = System.Net.NetworkInformation.IPGlobalProperties
                        .GetIPGlobalProperties()
                        .GetActiveTcpListeners()
                        .Where(ep => ep.Port == 8445)
                        .Select(ep => ep.ToString())
                        .ToArray();

                    _logger.LogInformation(
                        "[MONITOR t+{Sec}s] UDP 41000-41999 bound: [{Udp}]  TCP 8445 listening: [{Tcp}]",
                        (i + 1) * 2,
                        udpLines.Length > 0 ? string.Join(", ", udpLines) : "NONE",
                        tcpLines.Length > 0 ? string.Join(", ", tcpLines) : "NONE");
                }
                catch (Exception monEx)
                {
                    _logger.LogWarning(monEx, "[MONITOR] Error checking ports");
                }
            }
        });

        call.OnUpdated += async (_, e) =>
        {
            var oldState = e.OldResource?.State?.ToString() ?? "null";
            var newState = e.NewResource?.State?.ToString() ?? "null";
            var resultInfo = e.NewResource?.ResultInfo;
            _logger.LogInformation(
                "[CALL-STATE] CallId={CallId} {OldState} → {NewState} | Code={Code} Subcode={Subcode} Message={Msg}",
                call.Id, oldState, newState,
                resultInfo?.Code, resultInfo?.Subcode, resultInfo?.Message);

            if (e.NewResource?.State != CallState.Established)
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
        _ = DisposeInternalAsync(CancellationToken.None);
    }

    private async Task DisposeInternalAsync(CancellationToken cancellationToken)
    {
        var bridges = new List<InCallSttBridge>();
        foreach (var key in _bridgesByCallId.Keys.ToArray())
        {
            if (_bridgesByCallId.TryRemove(key, out var bridge))
            {
                bridges.Add(bridge);
            }
        }

        var disposeTasks = bridges
            .Select(async bridge =>
            {
                try
                {
                    await bridge.DisposeAsync().ConfigureAwait(false);
                }
                catch
                {
                    // ignore
                }
            })
            .ToArray();

        if (disposeTasks.Length > 0)
        {
            try
            {
                await Task.WhenAll(disposeTasks).WaitAsync(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
            }
            catch
            {
                // ignore shutdown timeout/cancellation
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
            _graphLogForwarder?.Dispose();
        }
        catch
        {
            // ignore
        }
        _graphLogForwarder = null;

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
