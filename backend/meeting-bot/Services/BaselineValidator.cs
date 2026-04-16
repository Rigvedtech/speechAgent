using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services;

public sealed class BaselineValidator
{
    private readonly GraphOptions _graph;
    private readonly MeetingBotOptions _bot;

    public BaselineValidator(IOptions<GraphOptions> graph, IOptions<MeetingBotOptions> bot)
    {
        _graph = graph.Value;
        _bot = bot.Value;
    }

    public IReadOnlyDictionary<string, object> Evaluate()
    {
        var checks = new Dictionary<string, object>
        {
            ["tenantIdConfigured"] = !string.IsNullOrWhiteSpace(_graph.TenantId),
            ["clientIdConfigured"] = !string.IsNullOrWhiteSpace(_graph.ClientId),
            ["clientSecretConfigured"] = !string.IsNullOrWhiteSpace(_graph.ClientSecret),
            ["callbackBaseUrlConfigured"] = Uri.TryCreate(_bot.CallbackBaseUrl, UriKind.Absolute, out _),
            ["callbackIsHttps"] = _bot.CallbackBaseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase),
            ["fixedGreetingConfigured"] = !string.IsNullOrWhiteSpace(_bot.FixedGreetingLine),
            ["manualValidationChecklist"] = new[]
            {
                "App registration set to multi-tenant",
                "Graph app permissions granted with admin consent",
                "Teams app manifest supports calling and validDomains are host-only",
                "Public callback URL is reachable from internet"
            }
        };

        var pass = checks.Where(kv => kv.Value is bool).All(kv => (bool)kv.Value);
        checks["status"] = pass ? "pass" : "fail";
        return checks;
    }
}
