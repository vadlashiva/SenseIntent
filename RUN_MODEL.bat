@echo off
REM Runs SensIntent, zero-shot and LLM-repair for one model. Usage: RUN_MODEL.bat <model id>
cd /d %~dp0code
set PY=
where python >nul 2>nul && set PY=python
if not defined PY ( where py >nul 2>nul && set PY=py -3 )
set M=%1
set TAG=%M:/=_%
if not exist ..\results\natural_v3 mkdir ..\results\natural_v3
%PY% run_eval.py sensintent ..\data\intents_natural.jsonl ..\results\natural_v3\sensintent_%TAG%.jsonl --provider groq --model %M%
if errorlevel 2 goto end
%PY% run_eval.py zeroshot   ..\data\intents_natural.jsonl ..\results\natural_v3\zeroshot_%TAG%.jsonl   --provider groq --model %M%
if errorlevel 2 goto end
%PY% run_eval.py llm_repair ..\data\intents_natural.jsonl ..\results\natural_v3\repair_%TAG%.jsonl     --provider groq --model %M%
:end
echo Finished or stopped for %M%. You can close this window.
