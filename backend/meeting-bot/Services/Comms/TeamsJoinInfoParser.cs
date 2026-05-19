using System.Collections.Generic;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Graph.Models;

namespace MeetingBot.Services.Comms;

internal static class TeamsJoinInfoParser
{
    /// <summary>Parses a Teams meetup-join URL into Graph models for <see cref="Microsoft.Graph.Communications.Calls.JoinMeetingParameters"/>.</summary>
    public static (ChatInfo ChatInfo, OrganizerMeetingInfo MeetingInfo, string TenantId) Parse(string joinUrl)
    {
        if (string.IsNullOrWhiteSpace(joinUrl))
        {
            throw new ArgumentException("joinUrl is required.", nameof(joinUrl));
        }

        var decoded = Uri.UnescapeDataString(joinUrl.Trim());
        var regex = new Regex(
            @"https://teams\.(microsoft|live)\.com[^\s""']*/meetup-join/(?<thread>[^/?]+)/(?<message>[^?""']+)\?context=(?<ctx>\{[^}]+\})",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

        var match = regex.Match(decoded);
        if (!match.Success)
        {
            throw new ArgumentException(
                "Join URL must be a Teams meetup-join link with ?context={Tid,Oid,...} (same format as Graph create call flow).",
                nameof(joinUrl));
        }

        var threadId = Uri.UnescapeDataString(match.Groups["thread"].Value);
        var messageId = Uri.UnescapeDataString(match.Groups["message"].Value);
        var contextJson = match.Groups["ctx"].Value;

        using var doc = JsonDocument.Parse(contextJson);
        var root = doc.RootElement;
        var tid = root.TryGetProperty("Tid", out var tidEl) ? tidEl.GetString() ?? string.Empty : string.Empty;
        var oid = root.TryGetProperty("Oid", out var oidEl) ? oidEl.GetString() ?? string.Empty : string.Empty;
        var replyChainMessageId = root.TryGetProperty("MessageId", out var midEl) ? midEl.GetString() : null;

        if (string.IsNullOrWhiteSpace(tid) || string.IsNullOrWhiteSpace(oid) ||
            string.IsNullOrWhiteSpace(threadId) || string.IsNullOrWhiteSpace(messageId))
        {
            throw new ArgumentException("Join URL context is missing Tid, Oid, thread, or message id.", nameof(joinUrl));
        }

        var chatInfo = new ChatInfo
        {
            ThreadId = threadId,
            MessageId = messageId,
            ReplyChainMessageId = string.IsNullOrWhiteSpace(replyChainMessageId) ? null : replyChainMessageId
        };

        var meetingInfo = new OrganizerMeetingInfo
        {
            Organizer = new IdentitySet
            {
                User = new Identity
                {
                    Id = oid,
                    AdditionalData = new Dictionary<string, object> { { "tenantId", tid } },
                },
            },
        };

        return (chatInfo, meetingInfo, tid);
    }
}
