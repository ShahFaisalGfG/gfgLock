function Get-AppMeta {
    <#
    .SYNOPSIS
        Returns app metadata from pyproject.toml as a PSObject.
    #>
    $py     = Join-Path $PSScriptRoot "read_meta.py"
    $result = python $py
    if ($LASTEXITCODE -ne 0) { throw "Failed to read app metadata from pyproject.toml" }
    return $result | ConvertFrom-Json
}
