@echo off
rem Cria a tarefa do Windows que baixa os precos a cada 20 minutos, sem abrir janela.
schtasks /create /f /tn "Goblinomics - atualizar precos" /sc minute /mo 20 /st 00:05 /tr "wscript.exe \"%~dp0silencioso.vbs\""
if errorlevel 1 goto falhou
echo.
echo Pronto: os precos serao baixados a cada 20 minutos.
echo Para desfazer, rode o desagendar.bat.
pause
exit /b 0
:falhou
echo.
echo Nao consegui criar a tarefa. Mostre esta janela ao Claude.
pause
exit /b 1
