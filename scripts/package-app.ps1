[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$artifactDirectory = Join-Path $projectRoot 'artifacts'
$archivePath = Join-Path $artifactDirectory 'app.zip'
$files = @(
    'BDACC_proj_1.py',
    'requirements.txt',
    'startup.sh',
    'data/constructors.csv',
    'data/drivers.csv',
    'data/driver_standings.csv',
    'data/qualifying.csv',
    'data/races.csv',
    'data/results.csv'
)

# Only application files enter the archive; Terraform state and credentials stay local.
foreach ($relativePath in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
        throw "Missing application file: $relativePath"
    }
}

New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [System.IO.File]::Open($archivePath, [System.IO.FileMode]::Create)
$archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relativePath in $files) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            (Join-Path $projectRoot $relativePath),
            $relativePath,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    $archive.Dispose()
    $stream.Dispose()
}

Write-Output $archivePath
