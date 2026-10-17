@echo off
cd /d %~dp0code
set PY=
where python >nul 2>nul && set PY=python
if not defined PY ( where py >nul 2>nul && set PY=py -3 )
%PY% score.py ..\data\intents_natural.jsonl ..\results\natural\default.jsonl ..\results\natural\rule.jsonl ..\results\natural\oracle.jsonl ..\results\natural_v3\*.jsonl
pause
