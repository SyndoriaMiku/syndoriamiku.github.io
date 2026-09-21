"""Batched, cached API suggestions. Recognition never depends on translation."""
import re
import unicodedata


def clean_suggestion(value):
    value = unicodedata.normalize('NFC', value or '').strip()
    if not value or re.search(r'[\u3400-\u9fff<>\ufffd]', value):
        return ''
    return ' '.join(value.strip('"“”‘’').split()).title()


class NameSuggestions:
    def __init__(self):
        self.cache = {}

    def fill(self, candidates, fetch, provider, limit=15000, batch_size=40):
        """fetch(list[str]) returns aligned readings, or raises on bad alignment.

        Retry alignment failures in smaller batches; never retry a transport
        failure once per name. Keep successes and expose failures for manual edit.
        """
        pending = list(dict.fromkeys(c['cn'] for c in candidates
                                     if (provider, c['cn']) not in self.cache))
        errors = []
        def request(names, depth=0):
            try:
                readings = fetch(names)
                if len(readings) != len(names):
                    raise ValueError('API trả lệch số dòng.')
            except ValueError as error:
                if len(names) > 1 and depth < 3:
                    half = len(names)//2
                    request(names[:half], depth+1)
                    request(names[half:], depth+1)
                else:
                    errors.append(str(error))
                return
            except Exception as error:
                errors.append(str(error))
                return
            for name, reading in zip(names, readings):
                cleaned = clean_suggestion(reading)
                if cleaned:
                    self.cache[provider, name] = cleaned
                else:
                    errors.append('API chưa trả bản dịch hợp lệ cho: ' + name)
            if len(self.cache) > 10000:
                for key in list(self.cache)[:len(self.cache)-10000]:
                    del self.cache[key]
        batch = []
        size = 0
        for name in pending:
            if len(name) > limit:
                errors.append('Tên dài hơn giới hạn API.')
                continue
            if batch and (len(batch) >= batch_size or size+len(name)+1 > limit):
                request(batch)
                if errors:
                    break
                batch, size = [], 0
            batch.append(name)
            size += len(name)+1
        else:
            if batch:
                request(batch)
        for candidate in candidates:
            candidate['suggested_vi'] = self.cache.get((provider, candidate['cn']), '')
        if errors:
            raise RuntimeError('Một số tên chưa có gợi ý. Có thể quét lại hoặc nhập thủ công.\n' + errors[0])
