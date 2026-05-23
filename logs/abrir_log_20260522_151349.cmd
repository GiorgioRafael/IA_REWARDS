@echo off
title AI Rewards - Log em tempo real
color 0A
echo Monitorando: "C:\Users\giorg\Documents\GitHub\AI_REWARDS\logs\execucao_20260522_151349.log"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath 'C:\Users\giorg\Documents\GitHub\AI_REWARDS\logs\execucao_20260522_151349.log' -Wait"
