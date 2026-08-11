param(
    [string] $WorkbookPath = "C:\TEMP\Aktivity*.xlsm",
    [string] $ApiUrl = "http://localhost:8000"
)

$workbook = Get-ChildItem -Path $WorkbookPath | Select-Object -First 1
if (-not $workbook) {
    throw "Workbook not found: $WorkbookPath"
}

$form = @{
    file = $workbook
}

Invoke-RestMethod -Method Post -Uri "$ApiUrl/imports/excel" -Form $form
