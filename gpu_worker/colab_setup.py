"""
Скрипт для запуска в Colab/Kaggle (одна ячейка).
Копирует gpu_worker/server.py в CosyVoice и поднимает туннель.
"""
import os, subprocess, sys, time, textwrap

def run(cmd, shell=True):
    print(f'$ {cmd}')
    subprocess.run(cmd, shell=shell, check=False)

# 1. CosyVoice
if not os.path.exists('CosyVoice'):
    run('git clone https://github.com/FunAudioLLM/CosyVoice.git')
    os.chdir('CosyVoice')
    run('pip install -q -r requirements.txt')
    os.chdir('..')
else:
    print('CosyVoice уже склонирован')

# 2. Установка cloudflared
if not os.path.exists('/tmp/cloudflared'):
    run('wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /tmp/cloudflared && chmod +x /tmp/cloudflared')

# 3. Запуск сервера
# Копируем наш сервер поверх оригинального (чтобы был /health)
import shutil
shutil.copy('Service/gpu_worker/server.py', 'CosyVoice/runtime/python/fastapi/server.py')
print('server.py скопирован')

# Запуск в фоне
run('nohup python CosyVoice/runtime/python/fastapi/server.py --port 50000 > /tmp/cosy.log 2>&1 &')
time.sleep(8)
run('curl -s http://localhost:50000/health || cat /tmp/cosy.log | tail -n 30')

# 4. Туннель
run('nohup /tmp/cloudflared tunnel --url http://localhost:50000 > /tmp/tunnel.log 2>&1 &')
time.sleep(6)
run('cat /tmp/tunnel.log | grep -o "https://.*trycloudflare.com" | head -n 1')
print('\nСкопируй URL выше в Service/.env как COSYVOICE_URL')
