; Inno Setup skript pro Raman Despiker
; 1) Sestav aplikaci:  python build_exe.py            (vytvoří dist\RamanDespiker\)
; 2) Nainstaluj Inno Setup: https://jrsoftware.org/isdl.php
; 3) Otevři tento soubor v Inno Setup a klikni Compile (nebo: iscc installer.iss)
; Výsledek: Output\RamanDespiker_Setup.exe  -> tohle pošli kolegům.

#define AppName "Raman Despiker"
#define AppVersion "1.0.0"
#define AppPublisher "Jakub Havranek"
#define AppExeName "RamanDespiker.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\RamanDespiker
DefaultGroupName=Raman Despiker
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=RamanDespiker_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Instalace bez admin práv (do profilu uživatele):
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; onedir build ze složky dist\RamanDespiker
Source: "dist\RamanDespiker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Raman Despiker"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Raman Despiker"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Vytvořit zástupce na ploše"; GroupDescription: "Zástupci:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Spustit Raman Despiker"; Flags: nowait postinstall skipifsilent
