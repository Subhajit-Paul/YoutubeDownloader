Unicode True

!ifndef VERSION
  !define VERSION "dev"
!endif

!define APP_NAME   "YouTube Downloader TUI"
!define APP_EXE    "youtube-tui.exe"
!define APP_ID     "YouTubeDownloaderTUI"
!define PUBLISHER  "Subhajit Paul"
!define REG_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

Name    "${APP_NAME}"
OutFile "release\youtube-tui-windows-x86_64-setup.exe"

InstallDir          "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey    HKLM "${REG_KEY}" "InstallDir"
RequestExecutionLevel admin
SetCompressor       /SOLID lzma

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "dist\${APP_EXE}"

  ; Start Menu shortcut opens via PowerShell so users get a proper terminal
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" \
    "-NoProfile -NoExit -Command `"& '$INSTDIR\${APP_EXE}'`"" \
    "$INSTDIR\${APP_EXE}" 0
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"

  ; Registry entries for Add/Remove Programs
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr  HKLM "${REG_KEY}" "DisplayName"         "${APP_NAME}"
  WriteRegStr  HKLM "${REG_KEY}" "DisplayVersion"      "${VERSION}"
  WriteRegStr  HKLM "${REG_KEY}" "Publisher"           "${PUBLISHER}"
  WriteRegStr  HKLM "${REG_KEY}" "InstallDir"          "$INSTDIR"
  WriteRegStr  HKLM "${REG_KEY}" "UninstallString"     '"$INSTDIR\uninstall.exe"'
  WriteRegStr  HKLM "${REG_KEY}" "DisplayIcon"         "$INSTDIR\${APP_EXE}"
  WriteRegDWORD HKLM "${REG_KEY}" "NoModify"           1
  WriteRegDWORD HKLM "${REG_KEY}" "NoRepair"           1
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir  "$INSTDIR"

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  DeleteRegKey HKLM "${REG_KEY}"
SectionEnd
