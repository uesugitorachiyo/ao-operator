param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$UbuntuHost,

    [Parameter(Position = 1)]
    [int]$LocalPort = $(if ($env:FACTORY_V3_TUNNEL_LOCAL_PORT) { [int]$env:FACTORY_V3_TUNNEL_LOCAL_PORT } else { 50051 }),

    [Parameter(Position = 2)]
    [int]$RemotePort = $(if ($env:FACTORY_V3_TUNNEL_REMOTE_PORT) { [int]$env:FACTORY_V3_TUNNEL_REMOTE_PORT } else { 50051 }),

    [Parameter(Position = 3)]
    [int]$WorkerRuntimeRemotePort = $(if ($env:FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT) { [int]$env:FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT } else { 0 }),

    [Parameter(Position = 4)]
    [int]$WorkerRuntimeLocalPort = $(if ($env:FACTORY_V3_WORKER_RUNTIME_LOCAL_PORT) { [int]$env:FACTORY_V3_WORKER_RUNTIME_LOCAL_PORT } elseif ($env:FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT) { [int]$env:FACTORY_V3_WORKER_RUNTIME_REMOTE_PORT } else { 0 })
)

$ErrorActionPreference = "Stop"

if ($env:FACTORY_V3_SSH_USER -and $UbuntuHost -notmatch "@") {
    $UbuntuHost = "$($env:FACTORY_V3_SSH_USER)@$UbuntuHost"
}

$ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
if (-not $ssh) {
    throw "ssh.exe was not found. Install OpenSSH Client or add OpenSSH-Win64 to PATH."
}

$baseArgs = @(
    "-N",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-L", "${LocalPort}:127.0.0.1:${RemotePort}"
)

if ($WorkerRuntimeRemotePort -gt 0) {
    if ($WorkerRuntimeLocalPort -le 0) {
        $WorkerRuntimeLocalPort = $WorkerRuntimeRemotePort
    }
    $baseArgs += @("-R", "${WorkerRuntimeRemotePort}:127.0.0.1:${WorkerRuntimeLocalPort}")
}

if ($env:FACTORY_V3_SSH_KEY) {
    $baseArgs = @("-i", $env:FACTORY_V3_SSH_KEY) + $baseArgs
}

while ($true) {
    Write-Host "cross-host-tunnel: forwarding 127.0.0.1:$LocalPort to $UbuntuHost:127.0.0.1:$RemotePort"
    if ($WorkerRuntimeRemotePort -gt 0) {
        Write-Host "cross-host-tunnel: reverse forwarding $UbuntuHost:127.0.0.1:$WorkerRuntimeRemotePort to worker 127.0.0.1:$WorkerRuntimeLocalPort"
    }
    & $ssh.Source @baseArgs $UbuntuHost
    $code = $LASTEXITCODE
    Write-Warning "cross-host-tunnel: ssh exited with code $code; restarting in 5 seconds"
    Start-Sleep -Seconds 5
}
