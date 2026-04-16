param(
    [string]$BaseUrl = "http://localhost:5213",
    [string]$RoomId = "gate-room-001",
    [string]$MeetingJoinUrl = "https://teams.microsoft.com/l/meetup-join/..."
)

$ErrorActionPreference = "Stop"

Write-Host "Gate 0: Baseline verification"
$baseline = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/baseline/verify"
$baseline | ConvertTo-Json -Depth 8

Write-Host "Gate 1: Join-only start call"
$startBody = @{
    roomId = $RoomId
    meetingJoinUrl = $MeetingJoinUrl
} | ConvertTo-Json
$start = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/meetings/start" -Body $startBody -ContentType "application/json"
$start | ConvertTo-Json -Depth 8

Write-Host "Gate 2: Speak-only is validated via callback event 'fixed-line-ready'"
Write-Host "Poll room state at /api/rooms and check event timeline."

Write-Host "Gate 3: Leave-only trigger"
$leaveBody = @{
    roomId = $RoomId
    reason = "validate-gates-script"
} | ConvertTo-Json
$leave = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/meetings/leave" -Body $leaveBody -ContentType "application/json"
$leave | ConvertTo-Json -Depth 8

Write-Host "Gate results: inspect /api/rooms for established -> fixed-line-ready -> call-ended transitions."
