namespace MeetingBot.Services;

public sealed class NullSttVoiceLoopStarter : ISttVoiceLoopStarter
{
    public void RequestStartAfterGreeting(string roomId)
    {
    }

    public Task StopAsync(string roomId, CancellationToken cancellationToken = default) => Task.CompletedTask;
}
