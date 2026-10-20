Set-Location $PSScriptRoot
python fetch.py *>> run.log
python tailor.py *>> run.log
$digest = "out\$(Get-Date -Format yyyy-MM-dd)\digest.html"
if (Test-Path $digest) { Start-Process $digest }
