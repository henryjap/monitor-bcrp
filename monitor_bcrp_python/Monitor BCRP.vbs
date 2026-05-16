Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = appDir & "\ejecutar_monitor.bat"
shell.Run """" & batPath & """", 2, False
