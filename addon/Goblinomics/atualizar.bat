@echo off
rem Baixa do site os precos mais novos para o Dados.lua desta pasta.
rem O jogo so le o arquivo novo ao entrar com o personagem ou com /reload.
setlocal
set "AQUI=%~dp0"
set "URL=https://gabrielbadolato.github.io/goblinomics/addon/Dados.lua"
if exist "%AQUI%Dados.novo" del "%AQUI%Dados.novo"
if exist "%AQUI%Dados.lua" goto so_se_mudou
curl -fsS --max-time 120 -o "%AQUI%Dados.novo" "%URL%"
goto baixou
:so_se_mudou
curl -fsS --max-time 120 -z "%AQUI%Dados.lua" -o "%AQUI%Dados.novo" "%URL%"
:baixou
if errorlevel 1 goto falhou
if not exist "%AQUI%Dados.novo" goto igual
findstr /c:"GoblinomicsDados" "%AQUI%Dados.novo" >nul
if errorlevel 1 goto invalido
move /y "%AQUI%Dados.novo" "%AQUI%Dados.lua" >nul
echo Goblinomics: dados atualizados.
exit /b 0
:igual
echo Goblinomics: os dados ja sao os mais novos.
exit /b 0
:invalido
del "%AQUI%Dados.novo"
echo Goblinomics: o arquivo baixado nao parece ser o de dados; mantive o anterior.
exit /b 1
:falhou
if exist "%AQUI%Dados.novo" del "%AQUI%Dados.novo"
echo Goblinomics: nao consegui baixar os dados; mantive os anteriores.
exit /b 1
