using MeetingBot.Middleware;
using MeetingBot.Models.Requests;
using MeetingBot.Models.Options;
using MeetingBot.Services;
using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<GraphOptions>(builder.Configuration.GetSection(GraphOptions.SectionName));
builder.Services.Configure<MeetingBotOptions>(builder.Configuration.GetSection(MeetingBotOptions.SectionName));
builder.Services.Configure<AiBridgeOptions>(builder.Configuration.GetSection(AiBridgeOptions.SectionName));
builder.Services.AddHttpClient();
builder.Services.AddHealthChecks();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddSingleton<RoomSessionStore>();
builder.Services.AddSingleton<GraphTokenProvider>();
builder.Services.AddSingleton<GraphCallsClient>();
builder.Services.AddSingleton<AiBridgeClient>();
builder.Services.AddSingleton<BaselineValidator>();
builder.Services.AddSingleton<CallLifecycleService>();

var app = builder.Build();
app.UseMiddleware<CorrelationIdMiddleware>();

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

app.MapPost("/api/calls/callback", async (HttpRequest request, CallLifecycleService lifecycle, ILoggerFactory loggerFactory, CancellationToken cancellationToken) =>
{
    using var reader = new StreamReader(request.Body);
    var payload = await reader.ReadToEndAsync(cancellationToken);
    var logger = loggerFactory.CreateLogger("GraphCallbackEndpoint");
    logger.LogInformation("Received Graph callback payload length: {PayloadLength}", payload.Length);
    await lifecycle.HandleCallbackAsync(payload, cancellationToken);
    return Results.Ok(new { received = true });
});

app.MapGet("/api/rooms", (RoomSessionStore store) => Results.Ok(store.GetAll()));

app.Run();
