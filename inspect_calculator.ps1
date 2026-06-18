param(
    [string]$Path = "C:\Users\ehakm\Documents\ELHApp-backend\Calculator_Builder..py",
    [string[]]$Patterns = @("<script", "</script>", "function ", "const ", "Math.", "45Z", "credit", "carbon")
)

$text = Get-Content -LiteralPath $Path -Raw
$lines = $text -split "`r?`n"

foreach ($pattern in $Patterns) {
    Write-Host "=== PATTERN: $pattern ==="
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -like "*$pattern*") {
            $start = [Math]::Max(0, $i - 3)
            $end = [Math]::Min($lines.Count - 1, $i + 6)
            for ($j = $start; $j -le $end; $j++) {
                "{0,6}: {1}" -f ($j + 1), $lines[$j]
            }
            Write-Host ""
            break
        }
    }
}
