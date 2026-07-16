; ═══════════════════════════════════════════════════════════════
;   Academy Manager Pro - Windows Installer (Inno Setup)
;   سیستم مدیریت آموزشگاه
;
;   ساخت: در Inno Setup 6 باز کنید و Compile بزنید
;   یا:  iscc installer.iss
; ═══════════════════════════════════════════════════════════════

#define MyAppName "سیستم مدیریت آموزشگاه"
#define MyAppNameEn "Academy Manager Pro"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "RAHSA Academic"
#define MyAppURL "https://rahsacademic.com"
#define MyAppExeName "AcademyManager.exe"

; مسیر خروجی PyInstaller (پوشه dist/AcademyManager)
#define MySourceDir "dist\AcademyManager"

[Setup]
; شناسه یکتا برای نصب‌کننده
AppId={{A7B3C4D5-E6F7-8901-ABCD-EF0123456789}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameEn} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
; فونت فارسی برای صفحات نصب
DefaultDialogFontName=Tahoma
LicenseFile=LICENSE.txt
; خروجی installer
OutputDir=installer_output
OutputBaseFilename=AcademyManager_Setup_v{#MyAppVersion}
; آیکون نصب‌کننده
SetupIconFile=static\images\icon.ico
; فشرده‌سازی
Compression=lzma2/ultra64
SolidCompression=yes
; ظاهر
WizardStyle=modern
WizardSizePercent=110
; نیاز به اجرا با دسترسی ادمین
PrivilegesRequired=admin
; زبان
ShowLanguageDialog=no
; ویژوال
DisableWelcomePage=no
DisableProgramGroupPage=no
; حذف فایل‌ها هنگام uninstall
UninstallDisplayName={#MyAppNameEn}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; اگر فایل فارسی Inno Setup را دارید، خط زیر را فعال کنید:
; Name: "persian"; MessagesFile: "compiler:Languages\Farsi.isl"
; دانلود: https://jrsoftware.org/files/istrans/Farsi-5.5.1.isl

[Tasks]
Name: "desktopicon"; Description: "ایجاد میانبر در دسکتاپ"; GroupDescription: "میانبرها:"
Name: "quicklaunchicon"; Description: "ایجاد میانبر در نوار وظیفه"; GroupDescription: "میانبرها:"; Flags: unchecked
Name: "startwithwindows"; Description: "اجرای خودکار هنگام روشن شدن ویندوز"; GroupDescription: "تنظیمات:"

[Files]
; فایل‌های اصلی برنامه از PyInstaller
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; منوی استارت
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\حذف {#MyAppNameEn}"; Filename: "{uninstallexe}"
; دسکتاپ
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; نوار وظیفه
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Registry]
; اجرای خودکار با ویندوز
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AcademyManager"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startwithwindows; Flags: uninsdeletevalue

[Run]
; اجرای برنامه پس از نصب
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای {#MyAppNameEn}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}\instance"
Type: filesandordirs; Name: "{app}\backups"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// ═══ صفحه خوش‌آمدگویی سفارشی ═══
var
  InfoPage: TNewStaticText;

procedure InitializeWizard;
begin
  // تنظیم عنوان پنجره
  WizardForm.Caption := '{#MyAppNameEn} - نصب‌کننده';
end;

// بررسی قبل از نصب
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  // بستن برنامه اگر در حال اجراست
  if FindWindowByClassName('Qt6QWindowIcon') <> 0 then
  begin
    if MsgBox('برنامه در حال اجراست. آیا می‌خواهید بسته شود؟', mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1000);
    end
    else
      Result := 'لطفاً ابتدا برنامه را ببندید.';
  end;
end;

// پیام پایان نصب
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // ایجاد پوشه‌های اضافی
    CreateDir('{app}\backups');
    CreateDir('{app}\static\uploads');
  end;
end;
