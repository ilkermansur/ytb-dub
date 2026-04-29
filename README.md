# 🎬 YTDub AI: Intelligent Video Dubbing Pipeline (MacOS)

[![Docker Image](https://img.shields.io/badge/docker-imansur/ytb--dub-blue?logo=docker)](https://hub.docker.com/r/imansur/ytb-dub)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg?logo=python)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-orange?logo=google-gemini)](https://ai.google.dev/)

**YTDub AI**, teknik videoları profesyonel düzeyde Türkçe'ye çeviren ve dublaj yapan, kendi kendine öğrenebilen zeki bir pipeline'dır. Karmaşık teknik terimleri (ACL, BGP, Jumbo Frames vb.) anlayan ve her çeviride kendini geliştiren bir mimariye sahiptir.

---

## 🔥 Temel Özellikler

### 🧠 Zeki Çeviri & AI Discovery
Sistem sadece bir çeviri aracı değil, bir **yerelleştirme mühendisidir**:
- **Fabrika Ayarlı Bilgi:** İçerisinde hazır mühürlenmiş **1350+ teknik terim** ve telaffuz sözlüğü ile gelir.
- **AI Discovery:** Çeviri sırasında yeni bir teknoloji veya framework ismi keşfederse bunu anında öğrenir.
- **Double-Pass Logic:** Yeni bir terim öğrenildiğinde, videoyu en baştan "tam tutarlılık" için tekrar çevirir.
- **Senkronize Telaffuz:** Yeni öğrenilen kelimeler otomatik olarak fonetik okunuşlarıyla telaffuz listesine eklenir.

### 🏗️ Modern Docker Mimarisi
- **Zero-Touch Provisioning:** Kurulum gerektirmez. Konteyner çalıştığı an gerekli tüm dosyaları Mac/PC tarafına hazırlar.
- **Garbage Collection:** İşlem bittiğinde geçici dosyaları temizler, sadece orijinal ve dublajlı videoyu bırakır.
- **NiceGUI Dashboard:** Tüm süreci canlı loglar ve bildirimlerle web arayüzünden yönetmenizi sağlar.

---

## 🚀 Hızlı Başlangıç

Sistemi ayağa kaldırmak için sadece bir `docker-compose.yml` dosyası yeterlidir.

### 1. Hazırlık
Bir klasör oluşturun ve içine şu `docker-compose.yml` dosyasını koyun:

```yaml
version: '3.8'
services:
  ytb-station:
    image: imansur/ytb-dub:latest
    container_name: ytb-dub-station
    ports:
      - "8080:8080"
    volumes:
      - ./ytb:/app/ytb
    restart: always
```

### 2. Çalıştırın
```bash
docker-compose up -d
```

### 3. Yapılandırma
Sistem açıldığında klasörünüzde otomatik olarak bir `ytb/` dizini oluşacaktır:
1. `ytb/.env` dosyasını açın ve `GEMINI_API_KEY=` kısmına kendi anahtarınızı yazın.
2. `http://localhost:8080` adresine gidin.
3. YouTube linkini yapıştırın ve **Dublajı Başlat** deyin!

---

## 🛠️ Klasör Yapısı & Özelleştirme

- **`ytb/config/translation_prompt.txt`**: Gemini'ye verilen "Anayasa" talimatları. Buradan dublajın tarzını değiştirebilirsiniz.
- **`ytb/config/glossary.json`**: AI tarafından keşfedilen teknik terimlerin listesi.
- **`ytb/config/pronunciation.json`**: Teknik terimlerin nasıl okunacağını belirleyen fonetik liste.
- **`ytb/data/`**: İndirilen videolar ve bitmiş dublajlar buradadır.

---

## 📈 Gelişim Döngüsü
YTDub AI kullandıkça güzelleşir. Her video çevirisi, kullanıcının `glossary.json` dosyasını zenginleştirir. Bu da bir sonraki çevirinin "daha zeki" ve "daha tutarlı" olmasını sağlar.

---

## 🤝 Katkıda Bulunma
Bu proje bir **Incremental Architect** tasarımıdır. Her katman, bir önceki katmanın başarısı üzerine inşa edilmiştir.

**Geliştirici:** [imansur](https://github.com/imansur)  
**Teknoloji:** Python, Docker, Gemini AI, XTTS v2, NiceGUI

---
*Not: Bu sistem teknik terimler (Networking, Cloud, DevOps) için optimize edilmiştir.*
