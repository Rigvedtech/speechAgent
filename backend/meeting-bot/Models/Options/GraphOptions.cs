namespace MeetingBot.Models.Options;

public sealed class GraphOptions
{
    public const string SectionName = "Graph";

    public string TenantId { get; init; } = string.Empty;

    public string ClientId { get; init; } = string.Empty;

    public string ClientSecret { get; init; } = string.Empty;

    public string Scope { get; init; } = "https://graph.microsoft.com/.default";

    /// <summary>
    /// Declared app registration tenant mode for baseline validation output.
    /// Supported values: SingleTenant, MultiTenant, Unknown.
    /// </summary>
    public string AppRegistrationTenantMode { get; init; } = "Unknown";
}
