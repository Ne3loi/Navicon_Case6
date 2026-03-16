@echo off
setlocal

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" "%ROOT%scripts\synthetic_test_harness.py" full
) else (
    python "%ROOT%scripts\synthetic_test_harness.py" full
)

echo.
echo Reports:
echo - %ROOT%test\synthetic_eval_report.md
echo - %ROOT%test\existing_docs_scan.md
echo - %ROOT%test\synthetic_redaction_smoke.zip
echo.
pause
