import os
import json
import argparse
import re
import httpx
from dotenv import load_dotenv

# .env yükle
load_dotenv()

def load_merged_config(filename, is_dict=True):
    """Hem fabrika ayarlarini hem kullanıcı ayarlarini birlestirir."""
    defaults_path = os.path.join("/app/defaults", filename)
    user_path = os.path.join("/app/config", filename)
    merged_data = {} if is_dict else []
    
    # 1. Önce Fabrika Ayarlarını Oku
    if os.path.exists(defaults_path):
        with open(defaults_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if is_dict: merged_data.update(data)
            else: merged_data.extend(data)
            
    # 2. Sonra Kullanıcı Ayarlarını Üzerine Yaz (Kullanıcı tercihi önceliklidir)
    if os.path.exists(user_path):
        with open(user_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if is_dict: merged_data.update(data)
            else: 
                for item in data:
                    if item not in merged_data: merged_data.append(item)
    return merged_data

def save_user_config(filename, new_items):
    """Sadece kullanıcıya özel keşfedilenleri kaydeder."""
    user_path = os.path.join("/app/config", filename)
    os.makedirs(os.path.dirname(user_path), exist_ok=True)
    existing_data = {} if isinstance(new_items, dict) else []
    if os.path.exists(user_path):
        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except: pass
            
    if isinstance(new_items, dict):
        existing_data.update(new_items)
    else:
        for item in new_items:
            if item not in existing_data: existing_data.append(item)
            
    with open(user_path, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)

def translate_batch_raw(api_key, transcript_chunk, glossary, start_idx=0, total_duration=None, model_name="gemini-2.5-flash", video_url="", progress_callback=None):
    """
    Dubbing Engine: Senin özel promptunla güçlendirilmiş versiyon.
    """
    input_data = [{"id": start_idx + i, "text": item["text"], "duration": item["duration"]} for i, item in enumerate(transcript_chunk)]
    
    duration_context = ""
    if total_duration:
        duration_context = f"\n[TIMING]: Bu bölümün tahmini süresi {sum(item['duration'] for item in transcript_chunk):.2f} sn."

    # Promptu defaults'tan oku (Kullanici degistirmisse config'den oku)
    prompt_path = os.path.join("/app/config", "translation_prompt.txt")
    if not os.path.exists(prompt_path):
        prompt_path = os.path.join("/app/defaults", "translation_prompt.txt")

    if not os.path.exists(prompt_path):
        return [], False

    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt = f.read()
        
    end_idx = start_idx + len(transcript_chunk) - 1
    prompt = prompt.replace("{duration_context}", duration_context)
    prompt = prompt.replace("{video_url}", video_url)
    prompt = prompt.replace("{glossary}", ", ".join(glossary) if glossary else "Yok")
    prompt = prompt.replace("{start_idx}", str(start_idx))
    prompt = prompt.replace("{end_idx}", str(end_idx))
    prompt = prompt.replace("{json_data}", json.dumps(input_data, ensure_ascii=False))

    clean_model = model_name.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1/models/{clean_model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            text = data['candidates'][0]['content']['parts'][0]['text']
            
            match = re.search(r'\{.*\}', text, re.DOTALL)
            res_json = json.loads(match.group()) if match else json.loads(text)
            
            new_terms = res_json.get("new_terms", {})
            found_new = False
            if new_terms:
                # Hem Fabrika hem Kullanici sozluklerini yukle (cakisma kontrolu icin)
                merged_glossary = load_merged_config("glossary.json", is_dict=False)
                merged_pronun = load_merged_config("pronunciation.json", is_dict=True)
                
                filtered_terms = {}
                for term, pron in new_terms.items():
                    # Eger kelime ne sozlukte ne de telaffuz listesinde yoksa 'yeni'dir
                    if term not in merged_glossary and term not in merged_pronun:
                        filtered_terms[term] = pron
                
                if filtered_terms:
                    try:
                        save_user_config("glossary.json", list(filtered_terms.keys()))
                        save_user_config("pronunciation.json", filtered_terms)
                        found_new = True
                        if progress_callback:
                            progress_callback(None, f"AI Discovery: {len(filtered_terms)} yeni terim öğrenildi.")
                    except Exception as ex:
                        print(f"[!] Discovery Kayıt Hatası: {ex}")

            return res_json.get("segments", []), found_new
    except Exception as e:
        error_msg = f"Çeviri Hatası: {str(e)}"
        if progress_callback: progress_callback(0, f"HATA: {error_msg}")
        return [], False

def translate(v_id, v_dir, progress_callback=None, total_duration=None, model_name="gemini-2.5-flash", video_url="", api_key=None):
    input_path = os.path.join(v_dir, "transcript_en.json")
    output_path = os.path.join(v_dir, "transcript_tr.json")
    
    if not os.path.exists(input_path): return False
    if not api_key: api_key = os.environ.get("GEMINI_API_KEY")
    if api_key: api_key = api_key.replace("GEMINI_API_KEY=", "").strip()
    if not api_key:
        if progress_callback: progress_callback(0, "HATA: API Key bulunamadi!")
        return False
        
    with open(input_path, 'r', encoding='utf-8') as f:
        full_transcript = json.load(f)

    chunk_size = 50
    total_chunks = (len(full_transcript) + chunk_size - 1) // chunk_size
    
    # --- 1. FAZ: DISCOVERY (KESIF) ---
    if progress_callback: progress_callback(0.1, "1. Faz: Terim keşfi ve ön çeviri yapılıyor...")
    
    current_glossary = load_merged_config("glossary.json", is_dict=False)
    any_new_terms = False
    first_pass_output = []
    
    for i in range(0, len(full_transcript), chunk_size):
        chunk = full_transcript[i:i + chunk_size]
        res, found = translate_batch_raw(api_key, chunk, current_glossary, start_idx=i, total_duration=total_duration, model_name=model_name, video_url=video_url, progress_callback=progress_callback)
        if found: any_new_terms = True
        first_pass_output.extend(res)

    # --- 2. FAZ: FINAL (EGER YENI TERIM VARSA) ---
    final_output = first_pass_output
    if any_new_terms:
        if progress_callback: progress_callback(0.5, "2. Faz: Yeni keşfedilen terimlerle tam tutarlılık için yeniden çevriliyor...")
        final_output = []
        updated_glossary = load_merged_config("glossary.json", is_dict=False)
        for i in range(0, len(full_transcript), chunk_size):
            chunk = full_transcript[i:i + chunk_size]
            res, _ = translate_batch_raw(api_key, chunk, updated_glossary, start_idx=i, total_duration=total_duration, model_name=model_name, video_url=video_url)
            final_output.extend(res)
    
    if not final_output:
        if progress_callback: progress_callback(0, "HATA: Çeviri başarısız!")
        return False
        
    final_transcript = []
    for segment in final_output:
        raw_ids = segment.get("ids", segment.get("id"))
        if raw_ids is None: continue
        ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        
        orig_segments = [full_transcript[idx] for idx in ids if idx < len(full_transcript)]
        if not orig_segments: continue
        
        new_start = orig_segments[0]["start"]
        new_duration = sum(seg["duration"] for seg in orig_segments)
        final_transcript.append({
            "start": new_start,
            "duration": new_duration,
            "text": segment["text"]
        })
        
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_transcript, f, ensure_ascii=False, indent=2)
        
    return True
