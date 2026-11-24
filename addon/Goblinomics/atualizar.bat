@echo off
rem Baixa do site os precos mais novos e o codigo do addon para esta pasta.
rem O jogo so le os arquivos novos ao entrar com o personagem ou com /reload
rem (arquivo que ainda nao existia so aparece depois de fechar e abrir o jogo).
setlocal
set "AQUI=%~dp0"
set "BASE=https://gabrielbadolato.github.io/goblinomics/addon/"
set "FALHA=0"
rem A lista do que baixar vem do site: uma linha por arquivo, "nome texto-que-ele-contem".
curl -fsS --max-time 60 -o "%AQUI%arquivos.novo" "%BASE%arquivos.txt"
if errorlevel 1 goto sem_lista
move /y "%AQUI%arquivos.novo" "%AQUI%arquivos.txt" >nul
goto com_lista
:sem_lista
if exist "%AQUI%arquivos.novo" del "%AQUI%arquivos.novo"
echo Goblinomics: nao consegui baixar a lista de arquivos.
if not exist "%AQUI%arquivos.txt" exit /b 1
:com_lista
for /f "usebackq tokens=1,2" %%a in ("%AQUI%arquivos.txt") do call :baixar %%a %%b
if "%FALHA%"=="1" exit /b 1
exit /b 0

rem :baixar <arquivo> <texto que o arquivo certo contem, ou - para nao conferir>
rem Baixa so se o do site for mais novo; um arquivo estranho nao substitui o que ja existe.
:baixar
rem So nomes simples terminados em .lua, .toc ou .tga: nada que o Windows execute, nada fora desta pasta.
echo %~1| findstr /r /i /c:"^[a-z0-9_-]*\.lua$" /c:"^[a-z0-9_-]*\.toc$" /c:"^[a-z0-9_-]*\.tga$" >nul
if errorlevel 1 goto b_nome
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
if "%~2"=="-" goto b_troca
findstr /c:"%~2" "%NOVO%" >nul
if errorlevel 1 goto b_invalido
:b_troca
move /y "%NOVO%" "%ARQ%" >nul
echo Goblinomics: %~1 atualizado.
goto :eof
:b_igual
echo Goblinomics: %~1 ja e o mais novo.
goto :eof
:b_nome
echo Goblinomics: %~1 nao e um nome de arquivo aceito; ignorado.
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
