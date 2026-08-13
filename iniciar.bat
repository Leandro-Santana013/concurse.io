@echo off
echo Iniciando o projeto concurse.io...

if exist venv\Scripts\activate.bat (
    echo Ativando ambiente virtual...
    call venv\Scripts\activate.bat
) else (
    echo Aviso: Ambiente virtual (venv) nao encontrado! Tentando usar o Python global...
)

echo Iniciando o servidor...
python app.py

echo.
echo O servidor parou ou ocorreu um erro.
pause
