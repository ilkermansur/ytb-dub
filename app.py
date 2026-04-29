import os
import asyncio
import json
from dotenv import load_dotenv

# .env dosyasini yukle (Mac tarafındaki ytb/.env ile senkron)
load_dotenv()

from nicegui import ui
from importlib import import_module

# Modül Yüklemeleri
ingest = import_module("01_ingest").ingest
translate = import_module("02_translate").translate
synthesize_mod = import_module("03_synthesize")
synthesize = synthesize_mod.synthesize
generate_audio_segment = synthesize_mod.generate_audio_segment

# Static dosya servisi
from nicegui import app
if not os.path.exists('data'):
    os.makedirs('data')
app.add_static_files('/data', 'data')

# --- AKILLI KURULUM (Smart Provisioning) ---
import shutil
def init_configs():
    # Yollar
    host_ytb = "/app/ytb"
    
    # Sadece gerekli klasörleri oluştur (Dosya kopyalama artik yok, defaults iceriden okunacak)
    os.makedirs(os.path.join(host_ytb, "config"), exist_ok=True)
    os.makedirs(os.path.join(host_ytb, "data"), exist_ok=True)
    
    # 1. Prompt dosyasini kopyala (Kullanici degistirebilsin)
    prompt_name = "translation_prompt.txt"
    target_prompt = os.path.join(host_ytb, "config", prompt_name)
    default_prompt = os.path.join("/app/defaults", prompt_name)
    
    if not os.path.exists(target_prompt) or os.path.getsize(target_prompt) == 0:
        if os.path.exists(default_prompt):
            try:
                with open(default_prompt, 'r', encoding='utf-8') as src:
                    content = src.read()
                with open(target_prompt, 'w', encoding='utf-8') as dst:
                    dst.write(content)
                print(f"[*] Prompt fabrikadan kopyalandi: {target_prompt}")
            except Exception as e:
                print(f"[!] Kopyalama Hatası: {e}")
    
    # 2. .env dosyasini olustur (Eger yoksa)
    env_path = os.path.join(host_ytb, ".env")
    if not os.path.exists(env_path):
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write("GEMINI_API_KEY=\n")
            print("[*] Yeni .env dosyasi olusturuldu.")
        except Exception as e:
            print(f"[!] .env oluşturma hatası: {e}")

    # 3. KOD UYUMLULUGU ICIN SYMLINK (Sembolik Bağ) OLUŞTUR
    for link_name in ["config", "data", ".env"]:
        target = os.path.join(host_ytb, link_name)
        link = os.path.join("/app", link_name)
        if os.path.exists(link) and not os.path.islink(link):
            if os.path.isdir(link): shutil.rmtree(link)
            else: os.remove(link)
        if not os.path.exists(link):
            os.symlink(target, link)

init_configs()

# --- YARDIMCI FONKSİYONLAR ---
# ... (load_config_file and save_config_file remain same)
def load_config_file(filename):
    path = os.path.join(os.path.dirname(__file__), "config", filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def save_config_file(filename, content):
    path = os.path.join(os.path.dirname(__file__), "config", filename)
    try:
        json.loads(content) # JSON doğrulaması
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        ui.notify(f"{filename} kaydedildi!", type='positive')
    except Exception as e:
        ui.notify(f"Hatalı JSON: {e}", type='negative')

# ... (GlobalState and run_flow remain same)
class GlobalState:
    running = False

state = GlobalState()

async def run_flow(mode, url, work_dir, api_key, model_name, original_vol):
    if not url:
        ui.notify("URL gerekli!")
        return
    
    def safe_log(text):
        try: log_area.push(text)
        except: pass

    def safe_notify(msg, type='info'):
        try: ui.notify(msg, type=type)
        except: pass
    
    state.running = True
    btn_dub.disable()
    btn_dl.disable()
    
    try:
        log_area.clear()
        safe_log(f"[*] İşlem Başlatıldı (Mod: {mode}, Model: {model_name})")
        
        def log_cb(p, t):
            safe_log(f"[*] {t}")
            if "AI Discovery" in t:
                safe_notify(t, type='positive')

        # 1. Ingest
        result = await asyncio.to_thread(ingest, url, work_dir, progress_callback=log_cb)
        video_list = result if isinstance(result, list) else [result] if result else []

        for v in video_list:
            v_id, v_dir, v_url = v['id'], v['dir'], v.get('url', '')
            safe_log(f"[+] Video Hazır: {v_id}")
            
            if mode == "full":
                safe_log(f"[*] {v_id} çevriliyor...")
                success = await asyncio.to_thread(translate, v_id, v_dir, progress_callback=log_cb, model_name=model_name, video_url=v_url, api_key=api_key)
                
                if not success:
                    safe_log(f"[!] {v_id} çeviri aşamasında başarısız oldu!")
                    continue
                
                safe_log(f"[*] {v_id} seslendiriliyor...")
                out_dir = os.path.join(work_dir, "output", v_id)
                await asyncio.to_thread(synthesize, v_id, v_dir, out_dir, progress_callback=log_cb, original_vol=original_vol/100)
                safe_log(f"[+] {v_id} TAMAMLANDI.")

                # --- GARBAGE COLLECTOR (Temizlik) ---
                try:
                    safe_log(f"[*] {v_id} temizleniyor...")
                    for f in os.listdir(v_dir):
                        # Sadece video dosyalarını koru (mp4, webm, mkv)
                        if not f.lower().endswith(('.mp4', '.webm', '.mkv')):
                            f_path = os.path.join(v_dir, f)
                            if os.path.isdir(f_path): shutil.rmtree(f_path)
                            else: os.remove(f_path)
                    safe_log(f"[+] {v_id} temizlendi, sadece orijinal video bırakıldı.")
                except Exception as clean_ex:
                    safe_log(f"[!] Temizlik hatası: {str(clean_ex)}")

        if mode == "download":
            safe_notify("İndirme İşlemi Tamamlandı!", type='positive')
        else:
            safe_notify("İşlem Tamamlandı!", type='positive')
    except Exception as e:
        safe_log(f"[!] HATA: {str(e)}")
        safe_notify(f"Hata: {str(e)}", type='negative')
    
    state.running = False
    try:
        btn_dub.enable()
        btn_dl.enable()
    except:
        pass

# --- UI TASARIMI ---
with ui.card().classes('w-full max-w-5xl mx-auto mt-6 p-8 shadow-2xl bg-white'):
    ui.label('IMansur YTDub').classes('text-3xl font-bold text-slate-800 mb-6')
    
    inp_url = ui.input('YouTube URL', placeholder='https://...').classes('w-full mb-4').props('outlined')
    
    with ui.row().classes('w-full gap-4 mb-4'):
        inp_key = ui.input('Gemini API Key (Veya ytb/.env dosyasini doldurun)', value=os.getenv("GEMINI_API_KEY", ""), password=True).classes('w-full').props('outlined')
    
    with ui.row().classes('w-full gap-4 mb-6 items-center'):
        ui.label('Model: Gemini 2.5 Flash (Sabit)').classes('flex-grow font-bold text-indigo-600')
        ui.label('Orijinal Ses %:')
        sld_vol = ui.slider(min=0, max=50, value=15).classes('w-32')
        ui.label().bind_text_from(sld_vol, 'value', backward=lambda v: f'{v}')

    with ui.row().classes('w-full gap-4 mb-8'):
        btn_dl = ui.button('SADECE İNDİR', on_click=lambda: run_flow("download", inp_url.value, "/app/data", inp_key.value, 'gemini-2.5-flash', sld_vol.value)).classes('flex-1 bg-slate-600 text-white h-14')
        btn_dub = ui.button('DUBLAJI BAŞLAT', on_click=lambda: run_flow("full", inp_url.value, "/app/data", inp_key.value, 'gemini-2.5-flash', sld_vol.value)).classes('flex-1 bg-indigo-600 text-white h-14 font-bold')

    # SÖZLÜK VE TELAFFUZ YÖNETİMİ (AÇILIR-KAPANIR)
    with ui.expansion('Sözlük ve Telaffuz Yönetimi', icon='settings_applications').classes('w-full mt-4 bg-slate-100 rounded border shadow-sm'):
        with ui.tabs().classes('w-full bg-slate-200 rounded-t') as dict_tabs:
            t_glossary = ui.tab('Glossary (Çeviri Koruması)', icon='translate')
            t_pronunc = ui.tab('Pronunciation (Okunuş)', icon='record_voice_over')
            t_tts_test = ui.tab('Edge-TTS Test', icon='volume_up')

        with ui.tab_panels(dict_tabs, value=t_glossary).classes('w-full border-t p-4 bg-slate-50'):
            with ui.tab_panel(t_glossary):
                ui.label('Teknik terimleri korur. Örn: ["FastAPI", "Python"]').classes('text-xs text-gray-500 mb-2')
                txt_glossary = ui.textarea(value=load_config_file("glossary.json")).classes('w-full font-mono').props('outlined')
                ui.button('Glossary Kaydet', on_click=lambda: save_config_file("glossary.json", txt_glossary.value)).classes('mt-2 bg-slate-700 text-white')

            with ui.tab_panel(t_pronunc):
                ui.label('Fonetik harita. Örn: {"Python": "paytın"}').classes('text-xs text-gray-500 mb-2')
                txt_pronunc = ui.textarea(value=load_config_file("pronunciation.json")).classes('w-full font-mono').props('outlined')
                ui.button('Telaffuz Kaydet', on_click=lambda: save_config_file("pronunciation.json", txt_pronunc.value)).classes('mt-2 bg-slate-700 text-white')

            with ui.tab_panel(t_tts_test):
                ui.label('Yazılan kelimenin telaffuzunu test edin.').classes('text-xs text-gray-500 mb-2')
                with ui.row().classes('w-full items-center gap-2'):
                    test_input = ui.input('Test Kelimesi/Cümlesi').classes('flex-grow').props('outlined')
                    audio_container = ui.row().classes('hidden') # Ses elemanı için konteyner
                    
                    async def play_test():
                        if not test_input.value:
                            ui.notify('Lütfen bir metin girin!', type='warning')
                            return
                        test_file_rel = os.path.join("data", "test_tts.mp3")
                        os.makedirs("data", exist_ok=True)
                        ui.notify('Ses üretiliyor...')
                        await generate_audio_segment(test_input.value, test_file_rel)
                        audio_container.clear()
                        with audio_container:
                            # Cache engellemek için timestamp ekliyoruz
                            ui.audio(f'/data/test_tts.mp3?v={os.path.getmtime(test_file_rel)}').props('autoplay')

                    ui.button('TEST ET', on_click=play_test).classes('bg-indigo-600 text-white h-14')

    ui.label('Canlı Loglar').classes('mt-8 font-bold text-slate-500')
    log_area = ui.log().classes('w-full h-80 bg-black text-green-400 p-4 font-mono text-xs rounded-lg')

try:
    ui.run(title='YTDub', port=8080, host='0.0.0.0', reload=False)
except KeyboardInterrupt:
    # Graceful Shutdown: Sistem kapatılırken oluşan gürültüyü engelle
    pass
