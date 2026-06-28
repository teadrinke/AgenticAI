$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $Root "frontend"
$Node = "C:\Users\acer\OneDrive - Society for Computer Technology & Research's\Desktop\NodeJS\node.exe"

Set-Location -LiteralPath $FrontendDir
& $Node .\node_modules\next\dist\bin\next dev -H 127.0.0.1 -p 3000
