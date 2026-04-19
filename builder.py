import requests, json, time, os, base64, datetime

# --- CẤU HÌNH ---
API_URL = "https://comic.sangtacvietcdn.xyz/tsm.php?cdn=/"
TEMPLATE_FILE = "reader.html" # File template bạn đã lưu từ bước trước
DELAY = 1.5                   # Nghỉ để tránh bị ban IP
CHUNK_LIMIT = 12000           # Mức an toàn để dịch không bị lỗi 413 hoặc timeout

def update_catalog(title, slug):
    catalog_path = os.path.join("stories", "list.json")
    catalog = []
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except: catalog = []

    # Nếu slug chưa có thì thêm mới, nếu có rồi thì cập nhật ngày
    existing = next((item for item in catalog if item['slug'] == slug), None)
    now = datetime.datetime.now()
    
    if not existing:
        catalog.append({
            "title": title,
            "slug": slug,
            "date": now.strftime("%d/%m/%Y"),
            "timestamp": now.timestamp()
        })
    else:
        existing['date'] = now.strftime("%d/%m/%Y")
        existing['timestamp'] = now.timestamp()

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=4)

def translate(text):
    headers = {
        "Origin": "https://www.bilibili.com",
        "Referer": "https://www.bilibili.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    }
    try:
        res = requests.post(API_URL, data={"sajax": "trans", "content": text}, headers=headers, timeout=45)
        return res.text.strip() if res.status_code == 200 else None
    except: return None

def build_story():
    txt_path = input("Kéo file .txt tiếng Trung vào: ").strip().replace('"', '').replace("'", "")
    slug = input("Nhập slug-name (VD: truyen-hay-01): ").strip()
    
    if not os.path.exists(txt_path) or not slug:
        print("Lỗi đường dẫn hoặc slug!"); return

    output_dir = os.path.join("stories", slug)
    os.makedirs(output_dir, exist_ok=True)

    with open(txt_path, "r", encoding="utf-8") as f:
        all_lines = [l.strip() for l in f.readlines() if l.strip()]

    story_data = {"title": slug.replace("-", " ").title(), "content": []}

    # Chia nhỏ thành các nhóm dòng (Chunks) dựa trên ký tự
    chunks = []
    current_group = []
    current_len = 0
    for line in all_lines:
        if current_len + len(line) < CHUNK_LIMIT:
            current_group.append(line)
            current_len += len(line)
        else:
            chunks.append(current_group)
            current_group = [line]
            current_len = len(line)
    chunks.append(current_group)

    print(f"--- Đang xử lý {len(chunks)} đợt dịch ---")
    
    for i, group in enumerate(chunks):
        input_text = "\n".join(group)
        vi_result = translate(input_text)
        
        if not vi_result:
            print(f"\n[!] Đợt {i+1} lỗi, đang nghỉ 5s rồi thử lại...")
            time.sleep(5)
            vi_result = translate(input_text) or ("[Lỗi dịch]\n" * len(group))

        vi_lines = vi_result.split('\n')
        
        # Ghép cặp từng dòng Trung - Việt
        for j in range(len(group)):
            cn = group[j]
            vi = vi_lines[j] if j < len(vi_lines) else ""
            
            story_data["content"].append({
                "cn": base64.b64encode(cn.encode('utf-8')).decode('utf-8'),
                "vi": base64.b64encode(vi.encode('utf-8')).decode('utf-8')
            })

        print(f"Tiến độ: {i+1}/{len(chunks)}", end="\r")
        time.sleep(DELAY)

    # Xuất file
    with open(os.path.join(output_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(story_data, f, ensure_ascii=False)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f_temp:
        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f_idx:
            f_idx.write(f_temp.read())
            
    update_catalog(story_data["title"], slug)
    print(f"\n✅ Hoàn thành! Đã cập nhật stories/{slug} và list.json")

if __name__ == "__main__":
    if not os.path.exists("stories"): os.makedirs("stories")
    build_story()