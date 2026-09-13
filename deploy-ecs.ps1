#!/usr/bin/env pwsh
<#
.SYNOPSIS
Builds and publishes an ECS service image, then registers a Fargate task revision.

.DESCRIPTION
Development only. The script creates the ECR repository when it is missing and
always pushes and registers the :latest image. It does not run a task or create
an ECS service; cron tasks are started by their scheduled Lambda.
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ServiceName,

    [string]$RepositoryName,
    [string]$TaskFamily,
    [string]$ContainerName,
    [string]$Dockerfile,
    [string]$TaskDefinitionTemplate
)

$ErrorActionPreference = 'Stop'
# The expected ECR "repository not found" response has a non-zero exit code.
# Handle AWS CLI exit codes explicitly below instead of letting PowerShell 7
# promote stderr from a native command to a terminating error.
$PSNativeCommandUseErrorActionPreference = $false
$AwsProfile = 'imhealth-dev'
$Region = 'ap-southeast-1'
$ApiRoot = Split-Path -Parent $PSCommandPath
$ServicePath = Join-Path $ApiRoot "services/$ServiceName"

function ConvertTo-TrimmedString([AllowNull()][object]$Value) {
    return ([string]$Value).Trim()
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) { throw 'AWS CLI is required.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
if (-not (Test-Path $ServicePath -PathType Container)) { throw "Service folder not found: $ServicePath" }

if ([string]::IsNullOrWhiteSpace($RepositoryName)) { $RepositoryName = "pupsrb-imhealth/$(ConvertTo-TrimmedString $ServiceName)" }
$EcrRepositoryName = ConvertTo-TrimmedString $RepositoryName
if ([string]::IsNullOrWhiteSpace($EcrRepositoryName)) { throw 'ECR repository name cannot be empty.' }
if (-not $TaskFamily) { $TaskFamily = "pupsrb-imhealth-$($ServiceName -replace '_', '-')" }
if (-not $ContainerName) { $ContainerName = $TaskFamily }
if (-not $Dockerfile) { $Dockerfile = Join-Path $ServicePath 'Dockerfile' }
if (-not $TaskDefinitionTemplate) { $TaskDefinitionTemplate = Join-Path $ServicePath 'ecs-task-definition.json' }
if (-not (Test-Path $Dockerfile -PathType Leaf)) { throw "Dockerfile not found: $Dockerfile" }
if (-not (Test-Path $TaskDefinitionTemplate -PathType Leaf)) { throw "Task definition template not found: $TaskDefinitionTemplate" }

$Aws = @('--profile', $AwsProfile, '--region', $Region)
$AccountId = ConvertTo-TrimmedString (& aws @Aws sts get-caller-identity --query Account --output text)
if ($LASTEXITCODE -ne 0 -or -not $AccountId) { throw 'Unable to resolve the imhealth-dev AWS account.' }
$TaskExecutionRoleArn = ConvertTo-TrimmedString (& aws @Aws ssm get-parameter --name '/pupsrb-imhealth/dev/iam/ecs_task_execution_role_arn' --query 'Parameter.Value' --output text)
if ($LASTEXITCODE -ne 0 -or -not $TaskExecutionRoleArn) { throw 'Unable to read the ECS task execution role ARN from development Parameter Store.' }
$TaskRoleArn = ConvertTo-TrimmedString (& aws @Aws ssm get-parameter --name '/pupsrb-imhealth/dev/iam/ecs_task_role_arn' --query 'Parameter.Value' --output text)
if ($LASTEXITCODE -ne 0 -or -not $TaskRoleArn) { throw 'Unable to read the ECS task role ARN from development Parameter Store.' }
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ImageUri = '{0}/{1}:latest' -f $Registry, $EcrRepositoryName
if ($ImageUri -notmatch '.+/.+:.+') { throw "Invalid ECR image URI: '$ImageUri'" }
Write-Host "Using ECR image: $ImageUri"

$PreviousErrorActionPreference = $ErrorActionPreference
try {
    # A missing repository is expected on the first run. PowerShell otherwise
    # promotes the AWS CLI's stderr to NativeCommandError before we can inspect it.
    $ErrorActionPreference = 'Continue'
    $DescribeOutput = & aws @Aws ecr describe-repositories --repository-names $EcrRepositoryName 2>&1
    $DescribeExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}
if ($DescribeExitCode -ne 0) {
    if (($DescribeOutput | Out-String) -notmatch 'RepositoryNotFoundException') {
        throw "Unable to inspect ECR repository '$EcrRepositoryName': $DescribeOutput"
    }
    & aws @Aws ecr create-repository --repository-name $EcrRepositoryName --image-scanning-configuration scanOnPush=true | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create ECR repository '$EcrRepositoryName'." }
}

& aws @Aws ecr get-login-password | docker login --username AWS --password-stdin $Registry
if ($LASTEXITCODE -ne 0) { throw 'ECR Docker login failed.' }

docker build --file $Dockerfile --tag $ImageUri $ApiRoot
if ($LASTEXITCODE -ne 0) { throw 'Docker build failed.' }
docker push $ImageUri
if ($LASTEXITCODE -ne 0) { throw 'Docker push failed.' }

$TaskDefinition = Get-Content $TaskDefinitionTemplate -Raw | ConvertFrom-Json
if ($null -eq $TaskDefinition) { throw "Task definition template '$TaskDefinitionTemplate' is empty or invalid." }
$TaskDefinition.family = $TaskFamily
$TaskDefinition.executionRoleArn = $TaskExecutionRoleArn
$TaskDefinition.taskRoleArn = $TaskRoleArn
$Container = @($TaskDefinition.containerDefinitions | Where-Object { $_.name -eq $ContainerName })
if ($Container.Count -ne 1) { throw "Expected exactly one '$ContainerName' container in $TaskDefinitionTemplate." }
$Container[0].image = $ImageUri
$LogConfiguration = $Container[0].logConfiguration
if ($null -eq $LogConfiguration -or $null -eq $LogConfiguration.options) {
    throw "Container '$ContainerName' must define an awslogs log configuration."
}
$LogGroupName = ConvertTo-TrimmedString $LogConfiguration.options.'awslogs-group'
if (-not $LogGroupName) { throw "Container '$ContainerName' must define an awslogs-group." }
$LogGroup = ConvertTo-TrimmedString (& aws @Aws logs describe-log-groups --log-group-name-prefix $LogGroupName --query "logGroups[?logGroupName=='$LogGroupName'].logGroupName" --output text)
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect CloudWatch log group '$LogGroupName'." }
if ($LogGroup -ne $LogGroupName) {
    & aws @Aws logs create-log-group --log-group-name $LogGroupName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create CloudWatch log group '$LogGroupName'." }
}

$TemporaryDefinition = Join-Path ([System.IO.Path]::GetTempPath()) ("$TaskFamily-$([guid]::NewGuid()).json")
try {
    $RenderedTaskDefinition = $TaskDefinition | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText(
        $TemporaryDefinition,
        $RenderedTaskDefinition,
        [System.Text.UTF8Encoding]::new($false)
    )
    $TaskDefinitionArn = ConvertTo-TrimmedString (& aws @Aws ecs register-task-definition --cli-input-json "file://$TemporaryDefinition" --query 'taskDefinition.taskDefinitionArn' --output text)
    if ($LASTEXITCODE -ne 0 -or -not $TaskDefinitionArn) { throw 'ECS task definition registration failed.' }
    Write-Host "Published $ImageUri"
    Write-Host "Registered $TaskDefinitionArn"
}
finally {
    Remove-Item -LiteralPath $TemporaryDefinition -Force -ErrorAction SilentlyContinue
}
