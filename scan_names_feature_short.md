# Feature: Scan Names / Quick Add to Glossary

## Mục tiêu

Thêm một feature vào công cụ dịch hiện tại để:

```text
Văn bản Trung
→ quét các cụm có khả năng là tên / thuật ngữ
→ hiển thị danh sách candidate
→ cho phép Add nhanh vào glossary hiện có
```

Không xây translator mới. Không thay đổi kiến trúc dịch hiện tại.

## Candidate cần quét

Ưu tiên:
- PERSON
- PLACE
- SECT / ORGANIZATION
- SKILL / TECHNIQUE
- ITEM
- TITLE
- UNKNOWN_TERM

Quan trọng nhất là PERSON.

## Logic quét đề xuất

Kết hợp nhiều tín hiệu nhẹ:

1. Chinese NER nếu project có thể tích hợp model nhỏ.
2. Heuristic họ Trung Quốc:
   - họ đơn: 林, 姜, 张, 李, 王, 赵...
   - họ kép: 欧阳, 司马, 上官, 诸葛...
3. Context pattern:
   - `X说道`
   - `X问道`
   - `X看着`
   - `X笑道`
   - `X师兄`
   - `X长老`
   - `X公子`
   - `X小姐`
4. Quét cụm chữ Hán lặp lại dài khoảng 2–6 ký tự.
5. Loại noise và các term đã có trong glossary.

Không cần LLM để scan mặc định.

## Output

Scanner trả về dạng:

```python
@dataclass
class NameCandidate:
    text: str
    entity_type: str | None
    count: int
    confidence: float
    contexts: list[str]
    suggested_translation: str | None
```

Ví dụ:

```json
[
  {
    "text": "林铭",
    "entity_type": "PERSON",
    "count": 18,
    "confidence": 0.96,
    "suggested_translation": "Lâm Minh"
  },
  {
    "text": "神凰岛",
    "entity_type": "PLACE",
    "count": 7,
    "confidence": 0.82,
    "suggested_translation": "Thần Hoàng Đảo"
  }
]
```

## UI

Thêm nút:

```text
Scan Names
```

Mở panel/modal dạng bảng:

| Chinese | Type | Count | Confidence | Suggested VI | Action |
|---|---|---:|---:|---|---|
| 林铭 | PERSON | 18 | 96% | Lâm Minh | Add |
| 神凰岛 | PLACE | 7 | 82% | Thần Hoàng Đảo | Add |

Action mỗi dòng:

```text
Add
Edit
Ignore
```

Nếu glossary hiện tại có lock thì thêm:

```text
Add & Lock
```

Click candidate nên hiện 1–3 context mẫu.

## Quick Add

Khi bấm Add:

```text
candidate
→ dùng suggested translation
→ user có thể sửa
→ add trực tiếp vào glossary hiện tại
```

Không tạo database glossary mới.

Phải reuse API/service/storage glossary hiện có.

## Suggested Translation

Nếu tool hiện tại đã có:
- Hán-Việt converter
- translation model
- glossary lookup

thì reuse chúng để tạo `suggested_translation`.

Priority:

```text
existing glossary/dictionary
→ Han-Viet converter
→ current translation service
```

Không cần xây translator riêng.

## Filtering

Không hiển thị mặc định:
- term đã có trong glossary
- pure number
- punctuation
- stopword quá phổ biến
- cụm score thấp và chỉ xuất hiện 1 lần
- noise chứa newline / ký tự rác

Cho phép false positive ở mức vừa phải; user sẽ quyết định Add hay Ignore.

## API chính

```python
def scan_name_candidates(
    text: str,
    existing_glossary: set[str] | None = None
) -> list[NameCandidate]:
    ...
```

Có thể tách:

```python
extract_candidates()
score_candidates()
classify_candidate()
suggest_translation()
```

## Scope MVP

Chỉ cần làm:

```text
[ ] Scan current chapter / selected text
[ ] Detect likely PERSON names
[ ] Detect repeated 2–6 Han-character terms
[ ] Surname heuristics
[ ] Basic context patterns
[ ] Count occurrences
[ ] Confidence score
[ ] Remove existing glossary entries
[ ] Show context examples
[ ] Suggested Vietnamese
[ ] Add / Edit / Ignore
[ ] Add directly into existing glossary
```

Chưa cần:
- alias merging
- multi-chapter global scan
- LLM classification
- auto add
- complex entity linking

## Yêu cầu cho Agent

Trước khi code, inspect project hiện tại để tìm:

```text
1. glossary storage/schema
2. API/service dùng để add glossary
3. nơi giữ current chapter/source text
4. translation/Han-Viet service hiện có
5. UI framework hiện tại
```

Sau đó tích hợp feature với thay đổi kiến trúc tối thiểu.

Không được:

```text
- rewrite translator
- tạo app mới
- tạo glossary system mới
- tự động add candidate mà không có user action
```

Target cuối cùng:

```text
Current Chinese chapter
→ Scan Names
→ Candidate list
→ Edit nếu cần
→ Add
→ Existing Glossary
```
