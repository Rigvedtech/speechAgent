using Azure.Communication.CallAutomation;
using MeetingBot.Models.Options;
using Microsoft.Extensions.Options;

namespace MeetingBot.Services.Acs;

/// <summary>Play audio and hang up via Call Automation SDK.</summary>
public sealed class AcsCallActionsService
{
    private readonly AcsOptions _acs;
    private readonly ILogger<AcsCallActionsService> _logger;
    private CallAutomationClient? _client;

    public AcsCallActionsService(IOptions<AcsOptions> acs, ILogger<AcsCallActionsService> logger)
    {
        _acs = acs.Value;
        _logger = logger;
    }

    private CallAutomationClient Client =>
        _client ??= new CallAutomationClient(_acs.ConnectionString);

    public async Task PlayAudioUriAsync(string callConnectionId, string audioUri, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(callConnectionId))
        {
            throw new ArgumentException("callConnectionId is required.", nameof(callConnectionId));
        }

        if (string.IsNullOrWhiteSpace(audioUri))
        {
            throw new ArgumentException("audioUri is required.", nameof(audioUri));
        }

        var callConnection = Client.GetCallConnection(callConnectionId);
        var media = callConnection.GetCallMedia();
        var fileSource = new FileSource(new Uri(audioUri));
        await media.PlayToAllAsync(new PlayToAllOptions(fileSource) { OperationContext = "bot-playback" }, cancellationToken)
            .ConfigureAwait(false);
        _logger.LogInformation("ACS PlayToAll requested for call {CallId} uri={Uri}", callConnectionId, audioUri);
    }

    public async Task HangUpAsync(string callConnectionId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(callConnectionId))
        {
            return;
        }

        try
        {
            var callConnection = Client.GetCallConnection(callConnectionId);
            await callConnection.HangUpAsync(forEveryone: true, cancellationToken: cancellationToken).ConfigureAwait(false);
            _logger.LogInformation("ACS hang up requested for call {CallId}", callConnectionId);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "ACS hang up failed for call {CallId}", callConnectionId);
            throw;
        }
    }
}
