param(
    [Parameter(Mandatory = $true)][string]$ExpectedZip,
    [string]$ResultsPath = (Join-Path $PSScriptRoot 'results.jsonl'),
    [string]$OutputPath = (Join-Path $PSScriptRoot 'comparison.json')
)

$ErrorActionPreference = 'Stop'
$metrics = [ordered]@{
    totalCost = 'score_cost'
    averageDeliveryTime = 'score_avg_time'
    success = 'score_success'
    complaintsSpawned = 'score_complaints'
    complaintsExpired = 'score_expired'
}

$expected = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
$commits = [System.Collections.Generic.HashSet[string]]::new()
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ExpectedZip))
try {
    foreach ($entry in $archive.Entries) {
        if ($entry.FullName -notmatch '^expected/[^/]+\.jsonl$') { continue }
        $reader = [IO.StreamReader]::new($entry.Open())
        try {
            while ($null -ne ($line = $reader.ReadLine())) {
                if (!$line.Trim()) { continue }
                $row = $line | ConvertFrom-Json
                if (!$row.case_id) { throw "Missing case_id in $($entry.FullName)" }
                foreach ($field in $metrics.Values) {
                    if ($null -eq $row.$field) { throw "Missing $field in $($row.case_id)" }
                }
                $expected.Add($row.case_id, $row)
                $null = $commits.Add($row.git_commit)
            }
        } finally {
            $reader.Dispose()
        }
    }
} finally {
    $archive.Dispose()
}

$expectedCount = $expected.Count
$policyIds = @(1..8)
$policyCounts = @{}
foreach ($id in $policyIds) {
    $policyCounts[$id] = [ordered]@{
        policyId = $id
        matchingCases = 0
        mismatchesByMetric = [ordered]@{}
    }
    foreach ($metric in $metrics.Keys) { $policyCounts[$id].mismatchesByMetric[$metric] = 0 }
}
$caseComparisons = @(
    foreach ($line in (Get-Content -LiteralPath $ResultsPath -Encoding UTF8)) {
        $run = $line | ConvertFrom-Json
        $baseline = $null
        if (!$expected.TryGetValue($run.case_id, [ref]$baseline)) {
            throw "Missing or duplicate case_id $($run.case_id)"
        }
        $null = $expected.Remove($run.case_id)
        $seenPolicies = [System.Collections.Generic.HashSet[int]]::new()
        $baselineMetrics = [ordered]@{}
        foreach ($metric in $metrics.Keys) { $baselineMetrics[$metric] = $baseline.($metrics[$metric]) }
        $variants = @(
            foreach ($variant in $run.variants) {
                $differences = [ordered]@{}
                foreach ($metric in $metrics.Keys) {
                    $actual = $variant.result.$metric
                    if ($null -eq $actual -or $actual -cne $baselineMetrics[$metric]) {
                        $differences[$metric] = $actual
                    }
                }
                foreach ($rawId in $variant.policyIds) {
                    $id = [int]$rawId
                    if (!$policyCounts.ContainsKey($id) -or !$seenPolicies.Add($id)) {
                        throw "Invalid or repeated policy $id in $($run.case_id)"
                    }
                    if (!$differences.Count) { $policyCounts[$id].matchingCases++ }
                    foreach ($metric in $differences.Keys) { $policyCounts[$id].mismatchesByMetric[$metric]++ }
                }
                [ordered]@{ policyIds = $variant.policyIds; differingReplayValues = $differences }
            }
        )
        if ($seenPolicies.Count -ne $policyIds.Count) { throw "Missing policies in $($run.case_id)" }
        [ordered]@{
            case_id = $run.case_id
            scenario_id = $run.scenario_id
            seed = $run.seed
            algorithm = $run.algorithm
            replan = $run.replan
            endTick = $run.variants[0].result.time
            expected = $baselineMetrics
            variants = $variants
        }
    }
)
if ($expected.Count) { throw "Missing replay results for $($expected.Count) cases" }
if ($caseComparisons.Count -ne 400) { throw "Expected 400 cases, found $($caseComparisons.Count)" }

$report = [ordered]@{
    baselineCommits = @($commits)
    expectedCases = $expectedCount
    matchedCaseIds = $caseComparisons.Count
    casesMatchingEveryPolicy = @($caseComparisons | Where-Object {
        @($_.variants | Where-Object { $_.differingReplayValues.Count }).Count -eq 0
    }).Count
    casesMatchingNoPolicy = @($caseComparisons | Where-Object {
        @($_.variants | Where-Object { $_.differingReplayValues.Count -eq 0 }).Count -eq 0
    }).Count
    policies = @($policyIds | ForEach-Object { $policyCounts[$_] })
    cases = $caseComparisons
}
$json = $report | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath),
    $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
[pscustomobject]$report | Select-Object -Property baselineCommits, expectedCases, matchedCaseIds,
    casesMatchingEveryPolicy, casesMatchingNoPolicy, policies | ConvertTo-Json -Depth 8
