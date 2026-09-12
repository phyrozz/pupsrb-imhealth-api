#!/usr/bin/env pwsh
# Usage: ./deploy.ps1 <stage> <service_name>
# Example: ./deploy.ps1 dev auth

param (
    [Parameter(Mandatory = $true)]
    [string]$Stage,
    [Parameter(Mandatory = $true)]
    [string]$ServiceName
)

$ErrorActionPreference = "Stop"

$ServicePath = "services/$ServiceName"

if (-not (Test-Path $ServicePath)) {
    Write-Host "Service folder not found: $ServicePath"
    exit 1
}

if (-not (Get-Command "serverless" -ErrorAction SilentlyContinue)) {
    Write-Host "'serverless' command not found. Make sure it's installed globally (npm i -g serverless)"
    exit 1
}

if ($Stage -eq "prod") {
    $AwsProfile = "imhealth-prod"
} elseif ($Stage -eq "dev") {
    $AwsProfile = "imhealth-dev"
} else {
    Write-Host "Unknown stage '$Stage'. Use 'dev' or 'prod'."
    exit 1
}

Write-Host "Deploying service '$ServiceName' to stage '$Stage' (profile: $AwsProfile)..."

Push-Location $ServicePath
try {
    $env:AWS_PROFILE = $AwsProfile
    serverless deploy --stage $Stage
}
catch {
    Write-Host "Deployment failed: $($_.Exception.Message)"
    Pop-Location
    exit 1
}
Pop-Location

Write-Host "Deployment complete for service '$ServiceName' ($Stage)"
