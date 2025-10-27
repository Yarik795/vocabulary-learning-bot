#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess
import sys

# Переходим в папку проекта
project_dir = os.getcwd()
print(f"[DIR] Рабочая папка: {project_dir}")

# Команды для инициализации Git
commands = [
    ["git", "init"],
    ["git", "config", "user.email", "you@example.com"],
    ["git", "config", "user.name", "Your Name"],
    ["git", "add", "-A"],
    ["git", "commit", "-m", "Initial commit: vocabulary-learning-bot"],
]

for cmd in commands:
    print(f"\n[>>] Выполняю: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, encoding='utf-8')
    
    if result.returncode != 0:
        print(f"[ERROR] {result.stderr}")
        if "not a git repository" not in result.stderr:
            sys.exit(1)
    else:
        if result.stdout.strip():
            print(f"[OK] {result.stdout.strip()}")

print("\n" + "="*60)
print("[OK] Git инициализирован успешно!")
print("="*60)
print("\nСледующие шаги для загрузки на GitHub:")
print("1. Создайте репозиторий: https://github.com/new")
print("   Название: vocabulary-learning-bot")
print("")
print("2. Выполните в папке проекта:")
print("")
print('   git remote add origin https://github.com/YOUR_USERNAME/vocabulary-learning-bot.git')
print("   git branch -M main")
print("   git push -u origin main")
