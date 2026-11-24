@echo off
rem Remove a tarefa criada pelo agendar.bat.
schtasks /delete /f /tn "Goblinomics - atualizar precos"
pause
