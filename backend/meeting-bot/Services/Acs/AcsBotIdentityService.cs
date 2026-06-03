using Azure.Communication.Identity;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services.Acs;

/// <summary>Ensures a stable ACS communication user id exists for outbound Teams joins.</summary>
public sealed class AcsBotIdentityService
{
    private readonly AcsOptions _acs;
    private readonly ILogger<AcsBotIdentityService> _logger;
    private string? _cachedUserId;

    public AcsBotIdentityService(IOptions<AcsOptions> acs, ILogger<AcsBotIdentityService> logger)
    {
        _acs = acs.Value;
        _logger = logger;
    }

    public async Task<string> GetOrCreateBotUserIdAsync(CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(_acs.BotCommunicationUserId))
        {
            return _acs.BotCommunicationUserId.Trim();
        }

        if (!string.IsNullOrWhiteSpace(_cachedUserId))
        {
            return _cachedUserId;
        }

        if (!_acs.IsConfigured)
        {
            throw new InvalidOperationException("Acs:ConnectionString is not configured.");
        }

        var identityClient = new CommunicationIdentityClient(_acs.ConnectionString);
        var user = await identityClient.CreateUserAsync(cancellationToken).ConfigureAwait(false);
        _cachedUserId = user.Value.Id;
        _logger.LogWarning(
            "Created ephemeral ACS bot user {UserId}. Set Acs__BotCommunicationUserId in .env to reuse this identity across restarts.",
            _cachedUserId);
        return _cachedUserId;
    }
}
