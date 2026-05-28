using DotNetEnv;
using MeetingBot.Middleware;
using MeetingBot.Models.Requests;
using MeetingBot.Models.Options;
using MeetingBot.Services;
using MeetingBot.Services.Comms;
using Microsoft.Extensions.Options;

// Allow repo .env to override stale machine/user env (NoClobber would keep e.g. MeetingBot__AutoLeaveSeconds=45).
Env.TraversePath().Load();
var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<GraphOptions>(builder.Configuration.GetSection(GraphOptions.SectionName));
builder.Services.Configure<MeetingBotOptions>(builder.Configuration.GetSection(MeetingBotOptions.SectionName));
builder.Services.Configure<MediaPlatformOptions>(builder.Configuration.GetSection(MediaPlatformOptions.SectionName));
builder.Services.Configure<AiBridgeOptions>(builder.Configuration.GetSection(AiBridgeOptions.SectionName));
builder.Services.AddHttpClient();
builder.Services.AddHealthChecks();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddSingleton<RoomSessionStore>();
builder.Services.AddSingleton<GraphTokenProvider>();
builder.Services.AddSingleton<GraphCallsClient>();
builder.Services.AddSingleton<AiBridgeClient>();
builder.Services.AddSingleton<ISttVoiceLoopStarter>(sp =>
{
    if (!OperatingSystem.IsWindows())
    {
        return new NullSttVoiceLoopStarter();
    }

    return new WindowsSttVoiceLoopStarter(
        sp.GetRequiredService<IOptions<MeetingBotOptions>>(),
        sp.GetRequiredService<RoomSessionStore>(),
        sp.GetRequiredService<IServiceScopeFactory>(),
        sp.GetRequiredService<ILogger<WindowsSttVoiceLoopStarter>>());
});
builder.Services.AddSingleton<BaselineValidator>();
builder.Services.AddSingleton<TeamsCommunicationsService>();
builder.Services.AddHostedService(sp => sp.GetRequiredService<TeamsCommunicationsService>());
builder.Services.AddSingleton<CallLifecycleService>();

var app = builder.Build();

app.Lifetime.ApplicationStarted.Register(() =>
{
    var mb = app.Services.GetRequiredService<IOptions<MeetingBotOptions>>().Value;
    var mp = app.Services.GetRequiredService<IOptions<MediaPlatformOptions>>().Value;
    var comms = app.Services.GetRequiredService<TeamsCommunicationsService>();
    app.Logger.LogInformation(
        "MeetingBot effective: AutoLeaveSeconds={AutoLeave}, EnableSttVoiceLoop={Stt}, SttSource={Src}, SttSuppressionAfterPlaySeconds={Supp}, SttMinWordCount={MinW}, UseApplicationHostedMedia={Hosted}, CommsClientActive={Comms}, MediaUdpRange={UdpMin}-{UdpMax}",
        mb.AutoLeaveSeconds,
        mb.EnableSttVoiceLoop,
        mb.SttLocalAudioSource,
        mb.SttSuppressionAfterPlaySeconds,
        mb.SttMinWordCount,
        mb.UseApplicationHostedMedia,
        comms.IsEnabled,
        mp.MediaPortMin,
        mp.MediaPortMax);
});

app.UseMiddleware<CorrelationIdMiddleware>();
app.UseStaticFiles();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.MapGet("/", () => Results.Ok(new
{
    service = "meeting-bot",
    status = "ok",
    purpose = "Teams no-AI join/callback/leave runtime"
}));

app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));
app.MapHealthChecks("/healthz");

app.MapGet("/api/baseline/verify", (BaselineValidator validator) =>
{
    return Results.Ok(validator.Evaluate());
});

app.MapPost("/api/meetings/start", async (StartMeetingRequest request, CallLifecycleService lifecycle, ILoggerFactory loggerFactory, CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("StartMeetingEndpoint");
    if (string.IsNullOrWhiteSpace(request.RoomId) || string.IsNullOrWhiteSpace(request.MeetingJoinUrl))
    {
        return Results.BadRequest(new { error = "roomId and meetingJoinUrl are required" });
    }

    var session = await lifecycle.StartAsync(request, cancellationToken);
    logger.LogInformation("Meeting start accepted for room {RoomId} with call {CallId}", session.RoomId, session.CallId);
    return Results.Ok(new
    {
        session.RoomId,
        session.CallId,
        status = session.Status.ToString(),
        session.StartedAtUtc
    });
});

app.MapPost("/api/meetings/create", async (CreateMeetingRequest request, GraphCallsClient graphCallsClient, IOptions<MeetingBotOptions> options, CancellationToken cancellationToken) =>
{
    var configuredOrganizer = options.Value.OrganizerUserIdOrUpn;
    var organizer = string.IsNullOrWhiteSpace(request.OrganizerUserIdOrUpn) ? configuredOrganizer : request.OrganizerUserIdOrUpn.Trim();
    if (string.IsNullOrWhiteSpace(organizer))
    {
        return Results.BadRequest(new { error = "organizerUserIdOrUpn is required in request or MeetingBot__OrganizerUserIdOrUpn config." });
    }

    var start = request.StartDateTimeUtc?.ToUniversalTime() ?? DateTimeOffset.UtcNow.AddMinutes(5);
    var end = request.EndDateTimeUtc?.ToUniversalTime() ?? start.AddMinutes(30);
    if (end <= start)
    {
        return Results.BadRequest(new { error = "endDateTimeUtc must be greater than startDateTimeUtc" });
    }

    var subject = string.IsNullOrWhiteSpace(request.Subject) ? "Bot test meeting via Graph" : request.Subject.Trim();
    var meeting = await graphCallsClient.CreateOnlineMeetingAsync(organizer, subject, start, end, cancellationToken);
    return Results.Ok(new
    {
        meetingId = meeting.MeetingId,
        joinWebUrl = meeting.JoinWebUrl,
        organizerUserIdOrUpn = organizer,
        startDateTimeUtc = meeting.StartDateTimeUtc,
        endDateTimeUtc = meeting.EndDateTimeUtc
    });
});

app.MapPost("/api/meetings/leave", async (LeaveMeetingRequest request, CallLifecycleService lifecycle, CancellationToken cancellationToken) =>
{
    var left = await lifecycle.LeaveAsync(request.RoomId, request.Reason, cancellationToken);
    return left
        ? Results.Ok(new { roomId = request.RoomId, status = "leave-requested", request.Reason })
        : Results.NotFound(new { error = "Room not found or call not initialized", roomId = request.RoomId });
});

app.MapPost("/api/rooms/{roomId}/turn", async (string roomId, SubmitTurnRequest request, CallLifecycleService lifecycle, CancellationToken cancellationToken) =>
{
    var result = await lifecycle.SubmitTurnAsync(roomId, request, cancellationToken);
    return result.Success
        ? Results.Ok(new { roomId, result.Message, result.TurnId, result.TraceId })
        : Results.BadRequest(new { roomId, error = result.Message, result.TurnId, result.TraceId });
});

app.MapPost("/api/calls/callback", async (HttpContext http, TeamsCommunicationsService comms, CallLifecycleService lifecycle, ILoggerFactory loggerFactory, CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("GraphCallbackEndpoint");
    if (comms.IsEnabled)
    {
        var sdkResponse = await comms.ProcessIncomingNotificationAsync(http.Request, cancellationToken).ConfigureAwait(false);
        if (sdkResponse is null)
        {
            http.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            return;
        }

        var body = sdkResponse.Content is null ? string.Empty : await sdkResponse.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        http.Response.StatusCode = (int)sdkResponse.StatusCode;
        http.Response.ContentType = sdkResponse.Content?.Headers.ContentType?.MediaType ?? "application/json; charset=utf-8";
        await http.Response.WriteAsync(body, cancellationToken).ConfigureAwait(false);
        return;
    }

    using var reader = new StreamReader(http.Request.Body);
    var payload = await reader.ReadToEndAsync().ConfigureAwait(false);
    logger.LogInformation("Received Graph callback payload length: {PayloadLength}", payload.Length);
    await lifecycle.HandleCallbackAsync(payload, cancellationToken).ConfigureAwait(false);
    http.Response.StatusCode = 200;
    await http.Response.WriteAsJsonAsync(new { received = true }, cancellationToken).ConfigureAwait(false);
});

app.MapGet("/api/rooms", (RoomSessionStore store) => Results.Ok(store.GetAll()));

app.Run();
