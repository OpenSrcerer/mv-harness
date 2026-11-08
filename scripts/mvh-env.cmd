@echo off
rem mv-harness shell environment (cmd twin of mvh-env.ps1).  Use:  call scripts\mvh-env.cmd [-Offline] [-Threads N]
rem No setlocal: the variables must survive in the caller's shell.
set "MVH_REPO=%~dp0.."
for %%I in ("%MVH_REPO%") do set "MVH_REPO=%%~fI"
set "MVH_HOME=%LOCALAPPDATA%\mvh"
set "MVH_PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "MVH_UVDIR=%APPDATA%\Python\Python312\Scripts"
set "MVH_FFBIN=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"

if not defined MVH_ENV_BASEPATH set "MVH_ENV_BASEPATH=%PATH%"
set "PATH=%MVH_FFBIN%;%MVH_PYDIR%;%MVH_PYDIR%\Scripts;%MVH_UVDIR%;%MVH_ENV_BASEPATH%"

set "TORCH_HOME=%MVH_HOME%\torch"
set "HF_HOME=%MVH_HOME%\hf"
set "AUDIO_SEPARATOR_MODEL_DIR=%MVH_HOME%\models\separator"
set "NUMBA_CACHE_DIR=%MVH_HOME%\numba"
set "NLTK_DATA=%MVH_HOME%\nltk"
set "MVH_MODELS_DIR=%MVH_HOME%\models"
set "UV_CACHE_DIR=%MVH_HOME%\uvcache"
set "XDG_CACHE_HOME=%MVH_HOME%\models\xdg"
set "MVH_RHUBARB=%MVH_HOME%\bin\rhubarb\Rhubarb-Lip-Sync-1.14.0-Windows\rhubarb.exe"
for %%D in ("%TORCH_HOME%" "%HF_HOME%" "%AUDIO_SEPARATOR_MODEL_DIR%" "%NUMBA_CACHE_DIR%" "%NLTK_DATA%" "%MVH_MODELS_DIR%" "%UV_CACHE_DIR%" "%MVH_HOME%\locks" "%MVH_HOME%\bin") do if not exist %%D mkdir %%D

set "MVH_FFMPEG=%MVH_FFBIN%\ffmpeg.exe"
set "MVH_FFPROBE=%MVH_FFBIN%\ffprobe.exe"
set "UV_PYTHON=%MVH_PYDIR%\python.exe"
set "UV_NO_SYNC=1"
set "PYTHONUTF8=1"
set "PYTHONPATH=%MVH_REPO%\src"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "HF_HUB_DISABLE_PROGRESS_BARS=1"
set "TOKENIZERS_PARALLELISM=false"

rem argument parsing: -Offline, -Threads N
set "MVH_OFFLINE_ARG="
:argloop
if "%~1"=="" goto argdone
if /I "%~1"=="-Offline" set "MVH_OFFLINE_ARG=1"
if /I "%~1"=="-Threads" ( set "MVH_THREADS=%~2" & shift )
shift
goto argloop
:argdone

if not defined MVH_THREADS set "MVH_THREADS=3"
set "OMP_NUM_THREADS=%MVH_THREADS%"
set "OPENBLAS_NUM_THREADS=%MVH_THREADS%"
set "MKL_NUM_THREADS=%MVH_THREADS%"
set "NUMBA_NUM_THREADS=%MVH_THREADS%"
set "VECLIB_MAXIMUM_THREADS=%MVH_THREADS%"
set "NUMEXPR_NUM_THREADS=%MVH_THREADS%"

if defined MVH_OFFLINE_ARG (
  set "HF_HUB_OFFLINE=1"
  set "TRANSFORMERS_OFFLINE=1"
  set "MVH_OFFLINE=1"
) else (
  set "HF_HUB_OFFLINE="
  set "TRANSFORMERS_OFFLINE="
  set "MVH_OFFLINE="
)
set "MVH_OFFLINE_ARG="
echo mvh-env: repo=%MVH_REPO% threads=%MVH_THREADS% ffmpeg=%MVH_FFMPEG%
