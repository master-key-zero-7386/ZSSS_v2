# ファイル名: backup_db.ps1
# 目的: ZSSSのPostgresデータベースを日次でダンプし、Googleドライブ配下に世代管理付きで保存する
# 使い方: タスクスケジューラから `powershell.exe -NoProfile -ExecutionPolicy Bypass -File backup_db.ps1` で実行
#         手動テスト時も同じコマンドでそのまま実行できる

param(
    [string]$BackupDir = "H:\マイドライブ\ZSSS_backup",
    [int]$RetentionDays = 30,
    [string]$PgDumpExe = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"
$LogFile = Join-Path $BackupDir "backup_log.txt"

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Output $line
    try {
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch {
        # ログ書き込み失敗（フォルダ未作成など）は致命的にしない
    }
}

function Read-DotEnv([string]$Path) {
    $result = @{}
    if (-not (Test-Path $Path)) {
        throw ".envファイルが見つかりません: $Path"
    }
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$key] = $value
    }
    return $result
}

try {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

    Write-Log "===== バックアップ開始 ====="

    if (-not (Test-Path $PgDumpExe)) {
        throw "pg_dump.exeが見つかりません: $PgDumpExe"
    }

    $envVars = Read-DotEnv -Path $EnvFile
    foreach ($required in @("PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DATABASE")) {
        if (-not $envVars.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($envVars[$required])) {
            throw ".envに $required が設定されていません"
        }
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outFile = Join-Path $BackupDir "zsss_backup_$timestamp.dump"

    $env:PGPASSWORD = $envVars["PG_PASSWORD"]
    try {
        & $PgDumpExe `
            -h $envVars["PG_HOST"] `
            -p $envVars["PG_PORT"] `
            -U $envVars["PG_USER"] `
            -d $envVars["PG_DATABASE"] `
            -F c `
            -f $outFile
        $exitCode = $LASTEXITCODE
    } finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    }

    if ($exitCode -ne 0) {
        if (Test-Path $outFile) { Remove-Item -Path $outFile -Force -ErrorAction SilentlyContinue }
        throw "pg_dumpが異常終了しました（終了コード: $exitCode）"
    }

    $size = (Get-Item $outFile).Length
    Write-Log ("バックアップ成功: {0} ({1:N1} MB)" -f $outFile, ($size / 1MB))

    # 世代管理: 保存期間を過ぎた古いバックアップを削除（成功時のみ実行）
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $oldFiles = Get-ChildItem -Path $BackupDir -Filter "zsss_backup_*.dump" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff }

    foreach ($old in $oldFiles) {
        try {
            Remove-Item -Path $old.FullName -Force
            Write-Log ("古いバックアップを削除: {0}" -f $old.Name)
        } catch {
            Write-Log ("古いバックアップの削除に失敗: {0} ({1})" -f $old.Name, $_.Exception.Message)
        }
    }

    Write-Log "===== バックアップ正常終了 ====="
    exit 0
} catch {
    Write-Log ("エラー: {0}" -f $_.Exception.Message)
    Write-Log "===== バックアップ異常終了 ====="
    exit 1
}
