param(
    [Parameter(Mandatory = $true)][string]$InputZip,
    [string]$OutputDirectory = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $InputZip))
try {
    & {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -notmatch '^(scenarios/[^/]+\.json|actions/[^/]+\.jsonl)$') {
                continue
            }
            $reader = [IO.StreamReader]::new($entry.Open())
            try {
                if ($entry.FullName.StartsWith('scenarios/')) {
                    [ordered]@{
                        kind = 'scenario'
                        data = $reader.ReadToEnd() | ConvertFrom-Json
                    } | ConvertTo-Json -Depth 20 -Compress
                    continue
                }
                while ($null -ne ($line = $reader.ReadLine())) {
                    if (!$line.Trim()) { continue }
                    $record = $line | ConvertFrom-Json
                    [ordered]@{
                        kind = 'actions'
                        data = $record | Select-Object case_id, scenario_id, scenario_sha256,
                            seed, preset, preset_params, algorithm, replan, actions
                    } | ConvertTo-Json -Depth 20 -Compress
                }
            } finally {
                $reader.Dispose()
            }
        }
    } | & node (Join-Path $PSScriptRoot 'replay.mjs') $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw "Replay failed with exit code $LASTEXITCODE" }
} finally {
    $archive.Dispose()
}
