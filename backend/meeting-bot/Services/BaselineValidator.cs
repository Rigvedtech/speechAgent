using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class BaselineValidator
{
    private readonly GraphOptions _graph;
    private readonly MeetingBotOptions _bot;
    private readonly AcsOptions _acs;

    public BaselineValidator(IOptions<GraphOptions> graph, IOptions<MeetingBotOptions> bot, IOptions<AcsOptions> acs)
    {
        _graph = graph.Value;
        _bot = bot.Value;
        _acs = acs.Value;
    }

    public IReadOnlyDictionary<string, object> Evaluate()
    {
        var checks = new Dictionary<string, object>
        {
            ["acsConnectionStringConfigured"] = _acs.IsConfigured,
            ["callbackBaseUrlConfigured"] = Uri.TryCreate(_bot.CallbackBaseUrl, UriKind.Absolute, out _),
            ["callbackIsHttps"] = _bot.CallbackBaseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase),
            ["sttWebSocketConfigured"] = !string.IsNullOrWhiteSpace(_bot.SttWebSocketUrl),
            ["fixedGreetingConfigured"] = !string.IsNullOrWhiteSpace(_bot.FixedGreetingLine),
            ["graphTenantConfigured"] = !string.IsNullOrWhiteSpace(_graph.TenantId),
            ["graphClientConfigured"] = !string.IsNullOrWhiteSpace(_graph.ClientId),
            ["manualValidationChecklist"] = new[]
            {
                "ACS resource has Teams interoperability enabled",
                "Callback URL reachable: {CallbackBaseUrl}/api/acs/events",
                "Media WebSocket reachable: wss://host/ws/acs-media",
                "Graph OnlineMeetings permission for /api/meetings/create (optional)",
                "Organizer set for meeting create: MeetingBot__OrganizerUserIdOrUpn"
            }
        };

        var pass = checks.Where(kv => kv.Value is bool).All(kv => (bool)kv.Value);
        checks["status"] = pass ? "pass" : "fail";
        return checks;
    }
}
