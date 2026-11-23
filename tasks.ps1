param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("up", "down", "unit", "integration", "test", "coverage", "lint")]
    [string]$Task
)

$ErrorActionPreference = "Stop"

switch ($Task) {
    "up" {
        & docker compose up --build -d
        exit $LASTEXITCODE
    }
    "down" {
        & docker compose down
        exit $LASTEXITCODE
    }
    "unit" {
        & uv run poe test
        exit $LASTEXITCODE
    }
    "integration" {
        & uv run poe test-integration
        exit $LASTEXITCODE
    }
    "test" {
        & uv run poe test
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        & uv run poe test-integration
        exit $LASTEXITCODE
    }
    "coverage" {
        & uv run poe cov
        exit $LASTEXITCODE
    }
    "lint" {
        & uv run poe lint
        exit $LASTEXITCODE
    }
}
