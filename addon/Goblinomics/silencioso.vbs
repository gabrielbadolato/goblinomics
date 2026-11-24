' Roda o atualizar.bat sem abrir janela (usado pela tarefa agendada).
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & pasta & "\atualizar.bat""", 0, False
