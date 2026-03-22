function Run-BackendLint {
    Write-Host "--- Backend: Linting ---" -ForegroundColor Cyan
    Set-Location backend
    uv run ruff check .
    Set-Location ..
}

function Run-FrontendLint {
    Write-Host "--- Frontend: Linting ---" -ForegroundColor Cyan
    Set-Location frontend
    npm run lint
    Set-Location ..
}

function Run-BackendFormat {
    Write-Host "--- Backend: Formatting ---" -ForegroundColor Cyan
    Set-Location backend
    uv run ruff format .
    Set-Location ..
}

function Run-FrontendFormat {
    Write-Host "--- Frontend: Formatting ---" -ForegroundColor Cyan
    Set-Location frontend
    npm run format
    Set-Location ..
}

function Run-BackendTest {
    Write-Host "--- Backend: Testing ---" -ForegroundColor Cyan
    Set-Location backend
    uv run pytest
    Set-Location ..
}

function Run-FrontendTest {
    Write-Host "--- Frontend: Testing ---" -ForegroundColor Cyan
    Set-Location frontend
    npm run test -- --run
    Set-Location ..
}

function Run-Coverage {
    Write-Host "--- Backend: Coverage ---" -ForegroundColor Cyan
    Set-Location backend
    uv run pytest --cov=app --cov-report=term-missing
    Set-Location ..

    Write-Host "--- Frontend: Coverage ---" -ForegroundColor Cyan
    Set-Location frontend
    npm run test:coverage
    Set-Location ..
}

$target = $args[0]

switch ($target) {
    "lint"     { Run-BackendLint; Run-FrontendLint }
    "format"   { Run-BackendFormat; Run-FrontendFormat }
    "test"     { Run-BackendTest; Run-FrontendTest }
    "coverage" { Run-Coverage }
    "check"    { Run-BackendLint; Run-FrontendLint; Run-BackendTest; Run-FrontendTest }
    default    {
        Write-Host "Usage: .\check.ps1 [lint | format | test | coverage | check]" -ForegroundColor Yellow
    }
}
