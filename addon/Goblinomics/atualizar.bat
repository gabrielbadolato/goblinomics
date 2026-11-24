@echo off
rem Baixa do site os precos mais novos e o codigo do addon para esta pasta.
rem O jogo so le os arquivos novos ao entrar com o personagem ou com /reload.
setlocal
set "AQUI=%~dp0"
set "BASE=https://gabrielbadolato.github.io/goblinomics/addon/"
set "FALHA=0"
call :baixar Dados.lua GoblinomicsDados
call :baixar Goblinomics.lua SLASH_GOBLINOMICS1
call :baixar Goblinomics.toc Interface
if "%FALHA%"=="1" exit /b 1
exit /b 0

rem :baixar <arquivo> <texto que o arquivo certo contem>
rem Baixa so se o do site for mais novo; um arquivo estranho nao substitui o que ja existe.
:baixar
set "ARQ=%AQUI%%~1"
set "NOVO=%AQUI%%~1.novo"
if exist "%NOVO%" del "%NOVO%"
if exist "%ARQ%" goto b_se_mudou
curl -fsS --max-time 120 -o "%NOVO%" "%BASE%%~1"
goto b_baixou
:b_se_mudou
curl -fsS --max-time 120 -z "%ARQ%" -o "%NOVO%" "%BASE%%~1"
:b_baixou
if errorlevel 1 goto b_falhou
if not exist "%NOVO%" goto b_igual
findstr /c:"%~2" "%NOVO%" >nul
if errorlevel 1 goto b_invalido
move /y "%NOVO%" "%ARQ%" >nul
echo Goblinomics: %~1 atualizado.
goto :eof
:b_igual
echo Goblinomics: %~1 ja e o mais novo.
goto :eof
:b_invalido
del "%NOVO%"
echo Goblinomics: %~1 baixado nao parece o arquivo certo; mantive o anterior.
set "FALHA=1"
goto :eof
:b_falhou
if exist "%NOVO%" del "%NOVO%"
echo Goblinomics: nao consegui baixar %~1; mantive o anterior.
set "FALHA=1"
goto :eof
