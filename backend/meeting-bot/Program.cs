using DotNetEnv;
using MeetingBot.Middleware;
using MeetingBot.Models.Options;
using MeetingBot.Models.Requests;
using MeetingBot.Services;
using MeetingBot.Services.Acs;
using Microsoft.Extensions.Options;
Env.TraversePath().Load();
var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<GraphOptions>(builder.Configuration.GetSection(GraphOptions.SectionName));
builder.Services.Configure<MeetingBotOptions>(builder.Configuration.GetSection(MeetingBotOptions.SectionName));
builder.Services.Configure<AcsOptions>(builder.Configuration.GetSection(AcsOptions.SectionName));
builder.Services.Configure<AiBridgeOptions>(builder.Configuration.GetSection(AiBridgeOptions.SectionName));
builder.Services.AddHttpClient();
builder.Services.AddHealthChecks();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddSingleton<RoomSessionStore>();
builder.Services.AddSingleton<GraphTokenProvider>();
builder.Services.AddSingleton<GraphMeetingClient>();
builder.Services.AddSingleton<GraphCallsClient>();
builder.Services.AddSingleton<AiBridgeClient>();
builder.Services.AddSingleton<AcsCallRegistry>();
builder.Services.AddSingleton<AcsBotIdentityService>();
builder.Services.AddSingleton<AcsCallJoinService>();
builder.Services.AddSingleton<AcsCallActionsService>();
builder.Services.AddSingleton<AcsMediaStreamingBridge>();
builder.Services.AddSingleton<AcsEventHandler>();
builder.Services.AddSingleton<BaselineValidator>();
builder.Services.AddSingleton<CallLifecycleService>();

var app = builder.Build();

app.Lifetime.ApplicationStarted.Register(() =>
{
    var mb = app.Services.GetRequiredService<IOptions<MeetingBotOptions>>().Value;
    var acs = app.Services.GetRequiredService<IOptions<AcsOptions>>().Value;
    app.Logger.LogInformation(
        "MeetingBot: JoinBackend={Join}, CallbackBaseUrl={Callback}, AcsConfigured={Acs}, MediaWsPath={Ws}, SttUrl={Stt}",
        mb.MeetingJoinBackend,
        mb.CallbackBaseUrl,
        acs.IsConfigured,
        acs.MediaWebSocketPath,
        mb.SttWebSocketUrl);
});

app.UseMiddleware<CorrelationIdMiddleware>();
app.UseWebSockets();
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
    architecture = "Graph Teams join (default) + ACS Call Automation (optional media/play)"
}));

app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));
app.MapHealthChecks("/healthz");

app.MapGet("/api/baseline/verify", (BaselineValidator validator) => Results.Ok(validator.Evaluate()));

app.MapPost("/api/meetings/start", async (
    StartMeetingRequest request,
    CallLifecycleService lifecycle,
    AcsCallJoinService acsJoin,
    IOptions<MeetingBotOptions> meetingOptions,
    ILoggerFactory loggerFactory,
    CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("StartMeetingEndpoint");
    var meeting = meetingOptions.Value;
    if (string.IsNullOrWhiteSpace(request.RoomId) || string.IsNullOrWhiteSpace(request.MeetingJoinUrl))
    {
        return Results.BadRequest(new { error = "roomId and meetingJoinUrl are required" });
    }

    if (!meeting.UseGraphJoin && !acsJoin.IsConfigured)
    {
        return Results.BadRequest(new { error = "ACS is not configured. Set Acs__ConnectionString and MeetingBot__CallbackBaseUrl (HTTPS), or use MeetingBot__MeetingJoinBackend=Graph." });
    }

    try
    {
        var session = await lifecycle.StartAsync(request, cancellationToken);
        logger.LogInformation(
            "{Backend} join initiated for room {RoomId} call {CallId}",
            session.JoinBackend,
            session.RoomId,
            session.CallId);
        var message = session.JoinBackend.Equals("Acs", StringComparison.OrdinalIgnoreCase)
            ? "ACS call created. Await CallConnected on /api/acs/events and media on WebSocket."
            : "Graph call created. Await established callback on /api/calls/callback.";
        return Results.Accepted(
            value: new
            {
                session.RoomId,
                session.CallId,
                joinBackend = session.JoinBackend,
                status = session.Status.ToString(),
                session.StartedAtUtc,
                message
            });
    }
    catch (Exception ex)
    {
        logger.LogError(ex, "ACS join failed for room {RoomId}", request.RoomId);
        return Results.Problem(detail: ex.Message, title: "Meeting join failed", statusCode: StatusCodes.Status502BadGateway);
    }
});

app.MapPost("/api/meetings/create", async (CreateMeetingRequest request, GraphMeetingClient graphMeetingClient, IOptions<MeetingBotOptions> options, CancellationToken cancellationToken) =>
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

    var subject = string.IsNullOrWhiteSpace(request.Subject) ? "Interview bot meeting" : request.Subject.Trim();
    var meeting = await graphMeetingClient.CreateOnlineMeetingAsync(organizer, subject, start, end, cancellationToken);
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
        ? Results.Ok(new { roomId = request.RoomId, status = "ended", request.Reason })
        : Results.NotFound(new { error = "Room not found", roomId = request.RoomId });
});

app.MapPost("/api/rooms/{roomId}/turn", async (string roomId, SubmitTurnRequest request, CallLifecycleService lifecycle, CancellationToken cancellationToken) =>
{
    var result = await lifecycle.SubmitTurnAsync(roomId, request, cancellationToken);
    return result.Success
        ? Results.Ok(new { roomId, result.Message, result.TurnId, result.TraceId })
        : Results.BadRequest(new { roomId, error = result.Message, result.TurnId, result.TraceId });
});

app.MapGet("/api/rooms", (RoomSessionStore store) => Results.Ok(store.GetAll()));

var acsOpts = app.Services.GetRequiredService<IOptions<AcsOptions>>().Value;
app.Map(acsOpts.MediaWebSocketPath, async (HttpContext context, AcsMediaStreamingBridge mediaBridge) =>
{
    if (!context.WebSockets.IsWebSocketRequest)
    {
        context.Response.StatusCode = StatusCodes.Status400BadRequest;
        await context.Response.WriteAsync("WebSocket required.");
        return;
    }

    var callConnectionId = context.Request.Headers["x-ms-call-connection-id"].FirstOrDefault();
    using var socket = await context.WebSockets.AcceptWebSocketAsync();
    await mediaBridge.HandleConnectionAsync(socket, callConnectionId, context.RequestAborted);
});

app.MapPost("/api/calls/callback", async (HttpContext http, CallLifecycleService lifecycle, ILoggerFactory loggerFactory, CancellationToken cancellationToken) =>
{
    using var reader = new StreamReader(http.Request.Body);
    var payload = await reader.ReadToEndAsync(cancellationToken).ConfigureAwait(false);
    var logger = loggerFactory.CreateLogger("GraphCallbackEndpoint");
    logger.LogInformation("Received Graph callback payload length: {PayloadLength}", payload.Length);
    await lifecycle.HandleCallbackAsync(payload, cancellationToken).ConfigureAwait(false);
    return Results.Ok(new { received = true });
});

app.MapPost(acsOpts.EventsCallbackPath, async (HttpContext http, AcsEventHandler handler, CancellationToken cancellationToken) =>
{
    using var reader = new StreamReader(http.Request.Body);
    var payload = await reader.ReadToEndAsync(cancellationToken).ConfigureAwait(false);
    await handler.HandlePayloadAsync(payload, cancellationToken).ConfigureAwait(false);
    return Results.Ok(new { received = true });
});

app.Run();
