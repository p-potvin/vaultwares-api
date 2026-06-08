$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$certDir = Join-Path $repoRoot '.certs'
$certFile = Join-Path $certDir 'localhost+127.0.0.1.pem'
$keyFile = Join-Path $certDir 'localhost+127.0.0.1-key.pem'

if (-not (Get-Command mkcert -ErrorAction SilentlyContinue)) {
    throw "mkcert is required. Install it first, then rerun this script."
}

New-Item -ItemType Directory -Force -Path $certDir | Out-Null

& mkcert -install
& mkcert -cert-file $certFile -key-file $keyFile localhost 127.0.0.1 ::1

Write-Host "Generated TLS certificate:" $certFile
Write-Host "Generated TLS key:" $keyFile
