@echo off
rem Cria (ou recria) a tarefa do Windows que confere os precos a cada 5 minutos, sem abrir janela.
rem Quase sempre ela so baixa uma lista de menos de 1 KB e termina; o arquivo de precos vem uma vez por hora.
schtasks /create /f /tn "Goblinomics - atualizar precos" /sc minute /mo 5 /st 00:00 /tr "wscript.exe \"%~dp0silencioso.vbs\""
if errorlevel 1 goto falhou
echo.
echo Pronto: os precos serao conferidos a cada 5 minutos.
echo Para desfazer, rode o desagendar.bat.
pause
exit /b 0
:falhou
echo.
echo Nao consegui criar a tarefa. Mostre esta janela ao Claude.
pause
exit /b 1
