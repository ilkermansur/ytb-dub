# Python 3.11 slim imaji uzerinden basliyoruz (Hafif ve Kararli)
FROM python:3.11-slim

# Calisma dizinini sabitle
WORKDIR /app

# Sistem bagimliliklarini kur (FFmpeg ses/video isleme için sart)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Fabrika ayarlarini (sözlükler ve promptlar) imajin icine gom
COPY config/ /app/defaults/

# Bagimlilik listesini kopyala ve kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodlarini kopyala
COPY . .

# NiceGUI portu
EXPOSE 8080

# Uygulamayi baslat
CMD ["python", "app.py"]
