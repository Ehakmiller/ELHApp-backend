$ErrorActionPreference = "Stop"

$NamespaceName = "calculator-data"
$KvKey = "calculator:data"
$ExportScript = "C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\45Z Calculator\export_lcfs_join_v2.py"
$JsonPath = "C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
$RepoRoot = "C:\Users\ehakm\Documents\ELHApp-backend"
$CondaExe = "C:\Users\ehakm\anaconda3\Scripts\conda.exe"
$PostExportScripts = @(
    "$RepoRoot\update_lcfs_json_canadian_fed_ci.py",
    "$RepoRoot\update_lcfs_json_bc_lcfs_ci.py",
    "$RepoRoot\update_lcfs_json_wa_lcfs_ci.py",
    "$RepoRoot\update_lcfs_json_regulatory_pathways.py",
    "$RepoRoot\update_lcfs_json_operating_permits.py",
    "$RepoRoot\build_wa_ca_calibration.py",
    "$RepoRoot\build_or_ca_calibration.py"
)

Write-Host "Running LCFS dropdown export..."
& $CondaExe run --no-capture-output -n ethanolq python $ExportScript

$env:LCFS_JSON_PATH = $JsonPath
foreach ($script in $PostExportScripts) {
    if (!(Test-Path -LiteralPath $script)) {
        throw "Post-export updater was not found: $script"
    }

    Write-Host "Applying post-export updater: $script"
    & $CondaExe run --no-capture-output -n ethanolq python $script
}

if (!(Test-Path -LiteralPath $JsonPath)) {
    throw "Export finished, but JSON was not found: $JsonPath"
}

$jsonItem = Get-Item -LiteralPath $JsonPath
Write-Host "JSON ready: $($jsonItem.FullName)"
Write-Host "Size: $($jsonItem.Length) bytes"
Write-Host "Modified: $($jsonItem.LastWriteTime)"

Write-Host "Looking up Cloudflare KV namespace: $NamespaceName"
$namespaceJson = npx.cmd wrangler kv namespace list
$namespaces = $namespaceJson | ConvertFrom-Json
$namespace = $namespaces | Where-Object { $_.title -eq $NamespaceName } | Select-Object -First 1

if (!$namespace) {
    throw "Could not find KV namespace named '$NamespaceName'. Check Wrangler login/account and namespace name."
}

Write-Host "Uploading to remote KV namespace '$NamespaceName' ($($namespace.id)) with key '$KvKey'..."
npx.cmd wrangler kv key put $KvKey --path $JsonPath --namespace-id $namespace.id --remote

Write-Host "Done. Uploaded '$JsonPath' to remote KV key '$KvKey' in namespace '$NamespaceName'."
