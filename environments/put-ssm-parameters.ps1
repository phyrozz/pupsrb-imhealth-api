param(
    [string]$Stage = "dev",
    [string]$Profile = "furk-dev",
    [string]$Region = "ap-southeast-1"
)

$ErrorActionPreference = "Stop"

function Assert-ValueIsSet {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.StartsWith("REPLACE_ME")) {
        throw "Set a real value for '$Name' before running this script."
    }
}

$prefix = "/pupsrb-imhealth/$Stage"

# Fill in the values below, then run:
#   .\environments\put-ssm-parameters.ps1
#
# To target another stage/profile:
#   .\environments\put-ssm-parameters.ps1 -Stage prod -Profile furk-prod
#
# Use SecureString for secrets. StringList is used for comma-separated list values.
$parameters = @(
    @{
        Name = "$prefix/apigw/authorizer_id"
        Type = "String"
        Value = "t5sx29"
    },
    @{
        Name = "$prefix/apigw/rest_api_id"
        Type = "String"
        Value = "gvrxndvfw5"
    },
    @{
        Name = "$prefix/apigw/rest_api_root_resource_id"
        Type = "String"
        Value = "dte2srxnh2"
    },
    @{
        Name = "$prefix/iam/lambda_role_arn"
        Type = "String"
        Value = "arn:aws:iam::549726193214:role/pupsrb-imhealth-lambda-role-dev"
    },
    @{
        Name = "$prefix/iam/ecs_task_execution_role_arn"
        Type = "String"
        Value = "arn:aws:iam::549726193214:role/pupsrb-imhealth-ecs-task-execution-role-dev"
    },
    @{
        Name = "$prefix/iam/ecs_task_role_arn"
        Type = "String"
        Value = "arn:aws:iam::549726193214:role/pupsrb-imhealth-ecs-task-role-dev"
    },
    @{
        Name = "$prefix/db/host"
        Type = "String"
        Value = "aws-1-ap-southeast-1.pooler.supabase.com"
    },
    @{
        Name = "$prefix/db/port"
        Type = "String"
        Value = "6543"
    },
    @{
        Name = "$prefix/db/name"
        Type = "String"
        Value = "postgres"
    },
    @{
        Name = "$prefix/db/user"
        Type = "String"
        Value = "postgres.xllrkaocacpnfabdszvl"
    },
    @{
        Name = "$prefix/db/password"
        Type = "SecureString"
        Value = "IA1exzof0BwBOMhV"
    },
    @{
        Name = "$prefix/s3/bucket_name"
        Type = "String"
        Value = "imhealth-storage-dev"
    },
    @{
        Name = "$prefix/ses/from_email"
        Type = "String"
        Value = "joshuamalabanan70@gmail.com"
    },
    @{
        Name = "$prefix/cron/secret"
        Type = "SecureString"
        Value = "&35w_L61`}cAylR(Kd"
    },
    @{
        Name = "$prefix/ecs/cluster"
        Type = "String"
        Value = "pup-imhealth-cluster-dev"
    },
    @{
        Name = "$prefix/ecs/subnets"
        Type = "String"
        Value = "subnet-0f1d56f5a1d6c9520,subnet-01635556ab13e08c5"
    },
    @{
        Name = "$prefix/ecs/security_groups"
        Type = "String"
        Value = "sg-0c05f0fcd99bf871d"
    },
    @{
        Name = "$prefix/cognito/user_pool_id"
        Type = "String"
        Value = "ap-southeast-1_I1M8CkRZ0"
    },
    @{
        Name = "$prefix/apigw/student_authorizer_id"
        Type = "String"
        Value = "75u0a5"
    }
)

foreach ($parameter in $parameters) {
    Assert-ValueIsSet -Name $parameter.Name -Value $parameter.Value

    Write-Host "Putting $($parameter.Name)"

    aws ssm put-parameter `
        --profile $Profile `
        --region $Region `
        --name $parameter.Name `
        --type $parameter.Type `
        --value $parameter.Value `
        --overwrite `
        | Out-Null
}

Write-Host "Done. Wrote $($parameters.Count) SSM parameters to $prefix using profile '$Profile'."
