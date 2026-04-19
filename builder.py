import requests, json, time, os, base64, datetime

# --- CẤU HÌNH ---
API_URL = "https://comic.sangtacvietcdn.xyz/tsm.php?cdn=/"
TEMPLATE_FILE = "reader.html"
DELAY = 1.5         # Tăng nhẹ delay lên vì gửi chunk lớn cần server xử lý lâu hơn
CHUNK_LIMIT = 10000 # Giới hạn 10.000 ký tự

def update_catalog(title, slug):
    catalog_path = os.path.join("stories", "list.json")
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    else:
        catalog = []

    if not any(item['slug'] == slug for item in catalog):
        catalog.append({
            "title": title,
            "slug": slug,
            "date": datetime.datetime.now().strftime("%d/%m/%Y"),
            "timestamp": datetime.datetime.now().timestamp()
        })
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=4)
        print("--- Đã cập nhật danh sách truyện ---")

def translate(text):
    try:
        # Giả lập header giống hệt extension để tránh bị chặn
        headers = {
            "Origin": "https://www.bilibili.com",
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        }
        res = requests.post(API_URL, data={"sajax": "trans", "content": text}, headers=headers, timeout=30)
        return res.text.strip() if res.status_code == 200 else None
    except Exception as e:
        print(f"\nLỗi kết nối: {e}")
        return None

def build_story():
    txt_path = input("Kéo file .txt vào đây: ").strip('"')
    slug = input("Nhập slug-name: ").strip()
    
    if not os.path.exists(txt_path) or not slug:
        print("Dữ liệu không hợp lệ!"); return

    output_dir = os.path.join("stories", slug)
    os.makedirs(output_dir, exist_ok=True)

    with open(txt_path, "r", encoding="utf-8") as f:
        all_lines = [l.strip() for l in f.readlines() if l.strip()]

    story_data = {"title": slug.replace("-", " ").title(), "content": []}

    # --- LOGIC CHIA CHUNK ---
    chunks = []
    current_chunk = ""
    for line in all_lines:
        if len(current_chunk) + len(line) < CHUNK_LIMIT:
            current_chunk += line + "\n"
        else:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
    if current_chunk:
        chunks.append(current_chunk)

    print(f"--- Đang dịch {len(chunks)} chunks (Mỗi chunk ~15k ký tự) ---")
    
    for i, chunk_text in enumerate(chunks):
        vi_text = translate(chunk_text)
        
        if not vi_text:
            print(f"\n[!] Chunk {i+1} lỗi hoặc server từ chối vì quá dài. Đang thử lại...")
            time.sleep(5)
            vi_text = translate(chunk_text) or "[Lỗi dịch sau khi thử lại]"

        # Encode Base64
        cn_enc = base64.b64encode(chunk_text.encode('utf-8')).decode('utf-8')
        vi_enc = base64.b64encode(vi_text.encode('utf-8')).decode('utf-8')
        
        story_data["content"].append({"cn": cn_enc, "vi": vi_enc})
        print(f"Tiến độ: {i+1}/{len(chunks)} hoàn thành.", end="\r")
        time.sleep(DELAY)

    # Ghi file
    with open(os.path.join(output_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(story_data, f, ensure_ascii=False)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f_temp:
        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f_idx:
            f_idx.write(f_temp.read())
            
    update_catalog(story_data["title"], slug)
    print(f"\n✅ Hoàn tất! Vào /stories/{slug} để kiểm tra.")

if __name__ == "__main__":
    build_story()