using System.IdentityModel.Tokens.Jwt;
using System.Net.Http.Headers;
using System.Security.Claims;
using Microsoft.Graph.Communications.Client.Authentication;
using Microsoft.Graph.Communications.Common;
using Microsoft.Graph.Communications.Common.Telemetry;
using Microsoft.Identity.Client;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;

namespace MeetingBot.Services.Comms;

/// <summary>Minimal IRequestAuthenticationProvider for Graph Communications Calling (from Microsoft sample pattern).</summary>
internal sealed class CommsAuthenticationProvider : ObjectRoot, IRequestAuthenticationProvider
{
    private const string TenantClaimUri = "http://schemas.microsoft.com/identity/claims/tenantid";
    /// <summary>Skype/Graph callback tokens are ~5 minutes; VMs under org policy often drift from NTP.</summary>
    private static readonly TimeSpan InboundTokenClockSkew = TimeSpan.FromMinutes(20);

    private readonly string _appId;
    private readonly string _appSecret;
    private readonly TimeSpan _openIdConfigRefreshInterval = TimeSpan.FromHours(2);
    private DateTime _prevOpenIdConfigUpdateTimestamp = DateTime.MinValue;
    private OpenIdConnectConfiguration? _openIdConfiguration;

    public CommsAuthenticationProvider(string appName, string appId, string appSecret, IGraphLogger logger)
        : base(logger.NotNull(nameof(logger)).CreateShim(nameof(CommsAuthenticationProvider)))
    {
        _appId = appId.NotNullOrWhitespace(nameof(appId));
        _appSecret = appSecret.NotNullOrWhitespace(nameof(appSecret));
    }

    public async Task AuthenticateOutboundRequestAsync(HttpRequestMessage request, string tenant)
    {
        const string resource = "https://graph.microsoft.com";
        tenant = string.IsNullOrWhiteSpace(tenant) ? "common" : tenant;
        var tokenLink = $"https://login.microsoftonline.com/{tenant}";
        var scopes = new[] { $"{resource}/.default" };

        GraphLogger.Info("CommsAuthenticationProvider: acquiring Graph token.");
        var app = ConfidentialClientApplicationBuilder.Create(_appId)
            .WithAuthority(tokenLink)
            .WithClientSecret(_appSecret)
            .Build();

        AuthenticationResult result;
        try
        {
            result = await app.AcquireTokenForClient(scopes).ExecuteAsync().ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            GraphLogger.Error(ex, "Failed to generate OAuth token for Communications client.");
            throw;
        }

        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", result.AccessToken);
    }

    public async Task<RequestValidationResult> ValidateInboundRequestAsync(HttpRequestMessage request)
    {
        var token = request.Headers.Authorization?.Parameter;
        if (string.IsNullOrWhiteSpace(token))
        {
            GraphLogger.Warn("Inbound callback rejected: missing Bearer token.");
            return new RequestValidationResult { IsValid = false };
        }

        const string authDomain = "https://api.aps.skype.com/v1/.well-known/OpenIdConfiguration";
        if (_openIdConfiguration is null ||
            DateTime.UtcNow > _prevOpenIdConfigUpdateTimestamp.Add(_openIdConfigRefreshInterval))
        {
            GraphLogger.Info("Updating OpenID configuration for inbound Graph notification validation.");
            var configurationManager = new ConfigurationManager<OpenIdConnectConfiguration>(
                authDomain,
                new OpenIdConnectConfigurationRetriever());
            _openIdConfiguration = await configurationManager.GetConfigurationAsync(CancellationToken.None).ConfigureAwait(false);
            _prevOpenIdConfigUpdateTimestamp = DateTime.UtcNow;
        }

        var validationParameters = new TokenValidationParameters
        {
            ValidIssuers = new[] { "https://graph.microsoft.com", "https://api.botframework.com" },
            ValidAudience = _appId,
            IssuerSigningKeys = _openIdConfiguration.SigningKeys,
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ClockSkew = InboundTokenClockSkew,
        };

        var handler = new JwtSecurityTokenHandler { MapInboundClaims = false };

        try
        {
            var principal = handler.ValidateToken(token, validationParameters, out var validatedToken);
            var jwt = validatedToken as JwtSecurityToken ?? handler.ReadJwtToken(token);
            var tenantId = ResolveTenantId(jwt, principal);
            if (string.IsNullOrEmpty(tenantId))
            {
                GraphLogger.Warn("Inbound callback rejected: tenant id (tid) missing after token validation.");
                return new RequestValidationResult { IsValid = false };
            }

#pragma warning disable CS0618
            request.Properties.Add(HttpConstants.HeaderNames.Tenant, tenantId);
#pragma warning restore CS0618
            return new RequestValidationResult { IsValid = true, TenantId = tenantId };
        }
        catch (Exception ex)
        {
            try
            {
                var jwt = handler.ReadJwtToken(token);
                var aud = jwt.Audiences.FirstOrDefault() ?? jwt.Subject ?? "(none)";
                GraphLogger.Error(
                    ex,
                    $"Failed to validate inbound notification token. iss={jwt.Issuer} aud={aud} nbf={jwt.ValidFrom:O} exp={jwt.ValidTo:O} utcNow={DateTime.UtcNow:O} clockSkewMin={InboundTokenClockSkew.TotalMinutes}");
            }
            catch
            {
                GraphLogger.Error(ex, "Failed to validate inbound notification token.");
            }

            return new RequestValidationResult { IsValid = false };
        }
    }

    private static string? ResolveTenantId(JwtSecurityToken jwt, ClaimsPrincipal? principal)
    {
        var fromJwt = FindTenantClaim(jwt.Claims);
        if (!string.IsNullOrEmpty(fromJwt))
        {
            return fromJwt;
        }

        return principal is null ? null : FindTenantClaim(principal.Claims);
    }

    private static string? FindTenantClaim(IEnumerable<Claim> claims)
    {
        foreach (var claim in claims)
        {
            if (claim.Type.Equals("tid", StringComparison.Ordinal) ||
                claim.Type.Equals(TenantClaimUri, StringComparison.Ordinal))
            {
                return claim.Value;
            }
        }

        return null;
    }
}
