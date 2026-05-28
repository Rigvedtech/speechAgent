namespace MeetingBot.Models.Options;

/// <summary>
/// Settings for Microsoft Teams application-hosted media (TCP/TLS). Required when <see cref="MeetingBotOptions.UseApplicationHostedMedia"/> is true.
/// </summary>
public sealed class MediaPlatformOptions
{
    public const string SectionName = "MediaPlatform";

    /// <summary>Certificate thumbprint (LocalMachine\My) used by the Skype Bots Media platform for TLS.</summary>
    public string CertificateThumbprint { get; init; } = string.Empty;

    /// <summary>Internal listening port for media on this instance.</summary>
    public int InstanceInternalPort { get; init; } = 8445;

    /// <summary>Public UDP/TCP port that Microsoft Teams platform uses to reach this bot (must match firewall / NAT).</summary>
    public int InstancePublicPort { get; init; } = 8445;

    /// <summary>Public IPv4 address for media (must match DNS if <see cref="ServiceFqdn"/> is used).</summary>
    public string InstancePublicIPAddress { get; init; } = string.Empty;

    /// <summary>Hostname placed in media platform config (should match the certificate CN/SAN).</summary>
    public string ServiceFqdn { get; init; } = string.Empty;

    /// <summary>UDP RTP port range (inclusive). Microsoft Teams media uses this range for audio; open on firewall/NAT.</summary>
    public int MediaPortMin { get; init; } = 41000;

    /// <summary>UDP RTP port range (inclusive). Must be &gt;= <see cref="MediaPortMin"/>.</summary>
    public int MediaPortMax { get; init; } = 41999;

    public bool IsComplete() =>
        !string.IsNullOrWhiteSpace(CertificateThumbprint) &&
        InstanceInternalPort > 0 &&
        InstancePublicPort > 0 &&
        !string.IsNullOrWhiteSpace(InstancePublicIPAddress) &&
        !string.IsNullOrWhiteSpace(ServiceFqdn) &&
        MediaPortMin > 0 &&
        MediaPortMax >= MediaPortMin;
}
