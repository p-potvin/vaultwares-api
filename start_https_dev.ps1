$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:SSL_CERTFILE = Join-Path $repoRoot '.certs\localhost+127.0.0.1.pem'
$env:SSL_KEYFILE = Join-Path $repoRoot '.certs\localhost+127.0.0.1-key.pem'
$env:API_HOST = if ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$env:API_PORT = if ($env:API_PORT) { $env:API_PORT } else { '8000' }

if (-not (Test-Path $env:SSL_CERTFILE) -or -not (Test-Path $env:SSL_KEYFILE)) {
    throw "Missing TLS certificate files. Run .\generate_local_tls_certs.ps1 first."
}

python api_server.py
