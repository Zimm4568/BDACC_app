[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('dev', 'prod')]
    [string]$Environment
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $workspace = terraform workspace show
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read the Terraform workspace.' }
    if ($workspace.Trim() -ne $Environment) {
        throw "Selected workspace is '$workspace'; select '$Environment' before deploying."
    }

    $rawOutputs = terraform output -json
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read Terraform outputs. Apply infrastructure first.' }
    $outputs = ($rawOutputs -join "`n") | ConvertFrom-Json
    if ($outputs.environment.value -ne $Environment) {
        throw 'Terraform outputs do not match the requested environment.'
    }
    foreach ($name in @('resource_group_name', 'web_app_name', 'subscription_id', 'web_app_url')) {
        if (-not $outputs.$name.value) { throw "Missing Terraform output: $name" }
    }

    $archivePath = Join-Path $projectRoot 'artifacts/app.zip'
    if (-not (Test-Path -LiteralPath $archivePath)) {
        throw 'Run scripts/package-app.ps1 first. Reuse that same ZIP when promoting dev to prod.'
    }

    az webapp deploy --subscription $outputs.subscription_id.value `
        --resource-group $outputs.resource_group_name.value `
        --name $outputs.web_app_name.value --src-path $archivePath --type zip --timeout 1200000
    if ($LASTEXITCODE -ne 0) { throw 'Azure deployment failed. Check the deployment logs.' }

    Write-Output "Dashboard: $($outputs.web_app_url.value)"
} finally {
    Pop-Location
}
