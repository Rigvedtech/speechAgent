namespace MeetingBot.Services.Acs;

internal static class AcsConnectionString
{
    public static (Uri Endpoint, string AccessKey) Parse(string connectionString)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("ACS connection string is required.", nameof(connectionString));
        }

        var values = connectionString
            .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(part => part.Split('=', 2))
            .Where(kv => kv.Length == 2)
            .ToDictionary(kv => kv[0], kv => kv[1], StringComparer.OrdinalIgnoreCase);

        if (!values.TryGetValue("endpoint", out var endpointRaw) ||
            !Uri.TryCreate(endpointRaw.TrimEnd('/'), UriKind.Absolute, out var endpoint))
        {
            throw new InvalidOperationException("ACS connection string is missing a valid endpoint= value.");
        }

        if (!values.TryGetValue("accesskey", out var accessKey) || string.IsNullOrWhiteSpace(accessKey))
        {
            throw new InvalidOperationException("ACS connection string is missing accesskey=.");
        }

        return (endpoint, accessKey);
    }
}
