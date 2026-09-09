"""
han_viet.py — Lookup tables for the Scan Names feature.
No external dependencies required.
"""

HAN_VIET: dict = {
    # Surnames
    '\u674e': 'Ly', '\u738b': 'Vuong', '\u5f20': 'Truong', '\u5218': 'Luu', '\u9648': 'Tran',
    '\u6768': 'Duong', '\u8d75': 'Trieu', '\u9ec4': 'Hoang', '\u5468': 'Chu', '\u5434': 'Ngo',
    '\u5f90': 'Tu', '\u5b59': 'Ton', '\u80e1': 'Ho', '\u6731': 'Chu', '\u9ad8': 'Cao',
    '\u6797': 'Lam', '\u4f55': 'Ha', '\u90ed': 'Quach', '\u9a6c': 'Ma', '\u7f57': 'La',
    '\u6881': 'Luong', '\u5b8b': 'Tong', '\u90d1': 'Trinh', '\u8c22': 'Ta', '\u97e9': 'Han',
    '\u5510': 'Duong', '\u51af': 'Phung', '\u4e8e': 'Vu', '\u8463': 'Dong', '\u8427': 'Tieu',
    '\u7a0b': 'Trinh', '\u66f9': 'Tao', '\u8881': 'Vien', '\u9093': 'Dang', '\u8bb8': 'Hua',
    '\u5085': 'Pho', '\u6c88': 'Tham', '\u66fe': 'Tang', '\u5f6d': 'Banh', '\u5415': 'La',
    '\u82cf': 'To', '\u5362': 'Lu', '\u848b': 'Tuong', '\u8521': 'Thai', '\u8d3e': 'Gia',
    '\u4e01': 'Dinh', '\u9b4f': 'Nguy', '\u8585': 'Tiet', '\u53f6': 'Diep', '\u960e': 'Diem',
    '\u4f59': 'Du', '\u6f58': 'Phan', '\u675c': 'Do', '\u6234': 'Dai', '\u590f': 'Ha',
    '\u9492': 'Chung', '\u6c6a': 'Uong', '\u7530': 'Dien', '\u4efb': 'Nhiem', '\u59dc': 'Khuong',
    '\u8303': 'Pham', '\u65b9': 'Phuong', '\u77f3': 'Thach', '\u59da': 'Dieu', '\u8c2d': 'Dam',
    '\u5ed6': 'Lieu', '\u90b9': 'Trau', '\u718a': 'Hung', '\u91d1': 'Kim', '\u9646': 'Luc',
    '\u90dd': 'Hac', '\u5b54': 'Khong', '\u767d': 'Bach', '\u5d14': 'Thoi', '\u5eb7': 'Khang',
    '\u6bdb': 'Mao', '\u90b1': 'Khau', '\u79e6': 'Tan', '\u6c5f': 'Giang', '\u53f2': 'Su',
    '\u987e': 'Co', '\u4faf': 'Hau', '\u90b5': 'Thieu', '\u5b5f': 'Manh', '\u9f99': 'Long',
    '\u4e07': 'Van', '\u6bb5': 'Doan', '\u96f7': 'Loi', '\u9322': 'Tien', '\u6c64': 'Thang',
    '\u5c39': 'Doan', '\u9ece': 'Le', '\u5e38': 'Thuong', '\u6b66': 'Vo', '\u8d3a': 'Ha',
    '\u8d56': 'Lai', '\u9f9a': 'Cung', '\u6587': 'Van', '\u4e54': 'Kieu', '\u6b27': 'Au',
    '\u6155': 'Mo', '\u5bb9': 'Dung', '\u53f8': 'Tu', '\u5b98': 'Quan', '\u8bf8': 'Chu',
    '\u845b': 'Cat', '\u4e1c': 'Dong', '\u72ec': 'Doc', '\u5b64': 'Co', '\u5357': 'Nam',
    '\u897f': 'Tay', '\u8f69': 'Hien', '\u8f95': 'Vien', '\u4ee4': 'Lenh', '\u72d0': 'Ho',
    '\u5c09': 'Uy', '\u8fdf': 'Tri', '\u752b': 'Phu', '\u767e': 'Bach',
    # Given name chars
    '\u9435': 'Minh', '\u4e91': 'Van', '\u96ea': 'Tuyet', '\u6708': 'Nguyet', '\u98ce': 'Phong',
    '\u5929': 'Thien', '\u5730': 'Dia', '\u5c71': 'Son', '\u6c34': 'Thuy',
    '\u706b': 'Hoa', '\u6728': 'Moc', '\u571f': 'Tho', '\u660e': 'Minh', '\u534e': 'Hoa',
    '\u82f1': 'Anh', '\u8c6a': 'Hao', '\u6770': 'Kiet', '\u5f3a': 'Cuong', '\u4f1f': 'Vi',
    '\u5cf0': 'Phong', '\u5b87': 'Vu', '\u6d69': 'Hao', '\u65ed': 'Huc', '\u9633': 'Duong',
    '\u5a77': 'Dinh', '\u83b9': 'Oanh', '\u5a1c': 'Na', '\u4e3d': 'Le', '\u82b3': 'Phuong',
    '\u96e8': 'Vu', '\u6674': 'Tinh', '\u68a6': 'Mong', '\u5f64': 'Dong', '\u73b2': 'Linh',
    '\u5026': 'Thien', '\u71d5': 'Yen', '\u6653': 'Hieu', '\u73ca': 'San',
    '\u6d1b': 'Lac', '\u82e5': 'Nhuoc', '\u8bd7': 'Thi', '\u52a0': 'Gia', '\u989c': 'Nhan',
    '\u67d4': 'Nhu', '\u9759': 'Tinh', '\u83f2': 'Phi', '\u51cc': 'Lang', '\u5ab3': 'Yen',
    '\u74a3': 'Ly', '\u73cd': 'Chan', '\u73c2': 'Kha', '\u7476': 'Dao', '\u777e': 'Can',
    '\u742a': 'Ky', '\u745e': 'Thuy', '\u7433': 'Lam', '\u7426': 'Ky',
    '\u9038': 'Dat', '\u660a': 'Hao', '\u8fb0': 'Than', '\u7139': 'Huyen',
    '\u7fca': 'Duc', '\u71d9': 'Hi', '\u6657': 'Thinh', '\u714e': 'Duc', '\u70e8': 'Diep',
    '\u9a8f': 'Tuan', '\u777f': 'Tue', '\u9706': 'Lam', '\u9716': 'Dinh', '\u9704': 'Tieu',
    '\u6cfd': 'Trach', '\u6de2': 'Ky', '\u6d9b': 'Dao', '\u6d66': 'Pho', '\u6d0b': 'Duong',
    '\u6f47': 'Tieu', '\u6f9c': 'Lan', '\u701a': 'Han', '\u6f20': 'Mac', '\u6e0a': 'Uyen',
    '\u6960': 'Nam', '\u6a17': 'Xuan', '\u67cf': 'Bach', '\u6953': 'Phong',
    '\u6850': 'Dong', '\u6842': 'Que', '\u677e': 'Tung',
    '\u7af9': 'Truc', '\u8377': 'Ha', '\u83ca': 'Cuc', '\u6885': 'Mai', '\u5170': 'Lan',
    '\u83b2': 'Lien', '\u8431': 'Huyen', '\u82d3': 'Linh',
    '\u8f89': 'Huy', '\u8000': 'Dieu', '\u5149': 'Quang', '\u4eae': 'Luong', '\u6628': 'Duc',
    '\u66dc': 'Dieu', '\u70dc': 'Vi', '\u708e': 'Viem', '\u70c8': 'Liet',
    '\u9a01': 'Hao', '\u52c7': 'Dung', '\u6bc5': 'Nghi', '\u521a': 'Cuong', '\u78ca': 'Loi',
    '\u946b': 'Han', '\u9e4f': 'Bang', '\u98de': 'Phi', '\u9e64': 'Hac', '\u9e3f': 'Hong',
    '\u864e': 'Ho', '\u8c79': 'Bao', '\u72fc': 'Lang', '\u9e9f': 'Lan',
    '\u86df': 'Giao',
    # Xianxia terms
    '\u4ed9': 'Tien', '\u9b54': 'Ma', '\u59d6': 'Yeu', '\u9b3c': 'Quy', '\u4f5b': 'Phat',
    '\u795e': 'Than', '\u5723': 'Thanh', '\u5e1d': 'De', '\u5c0a': 'Ton', '\u541b': 'Quan',
    '\u9053': 'Dao', '\u5fb7': 'Duc',
    '\u5b97': 'Tong', '\u95e8': 'Mon', '\u6d3e': 'Phai', '\u6559': 'Giao', '\u6bbf': 'Dien',
    '\u9601': 'Cac', '\u5c9b': 'Dao', '\u57ce': 'Thanh', '\u56fd': 'Quoc', '\u754c': 'Gioi',
    '\u57df': 'Vuc', '\u6d77': 'Hai', '\u6e56': 'Ho', '\u6cb3': 'Ha', '\u5cb3': 'Nhac',
    '\u5251': 'Kiem', '\u5200': 'Dao', '\u67aa': 'Thuong', '\u5f13': 'Cung',
    '\u529f': 'Cong', '\u6cd5': 'Phap', '\u8bc0': 'Quyet', '\u672f': 'Thuat',
    '\u4e39': 'Dan', '\u836f': 'Duoc', '\u7075': 'Linh', '\u6c14': 'Khi', '\u529b': 'Luc',
    '\u5143': 'Nguyen', '\u771f': 'Chan', '\u4fee': 'Tu', '\u70bc': 'Luyen',
    '\u5883': 'Canh', '\u9636': 'Giai', '\u54c1': 'Pham', '\u7ea7': 'Cap', '\u5c42': 'Tang',
    '\u53e4': 'Co', '\u592a': 'Thai', '\u5927': 'Dai', '\u5c0f': 'Tieu', '\u8001': 'Lao',
    '\u5c11': 'Thieu', '\u65b0': 'Tan', '\u5148': 'Tien', '\u540e': 'Hau',
    '\u5185': 'Noi', '\u5916': 'Ngoai', '\u6b63': 'Chinh', '\u90aa': 'Ta',
    '\u9634': 'Am', '\u4e7e': 'Can', '\u5764': 'Khon', '\u79bb': 'Ly',
    '\u9b54': 'Ma', '\u6df7': 'Hon',
    '\u865a': 'Hu', '\u7a7a': 'Khong', '\u65e0': 'Vo', '\u6709': 'Huu', '\u7384': 'Huyen',
    '\u8d64': 'Xich', '\u9752': 'Thanh', '\u7d2b': 'Tu', '\u7389': 'Ngoc',
    # Titles
    '\u5e08': 'Su', '\u7236': 'Phu', '\u6bcd': 'Mau', '\u5144': 'Huynh', '\u5f1f': 'De',
    '\u59d0': 'Ty', '\u59b9': 'Muoi', '\u4e3b': 'Chu', '\u638c': 'Chuong',
    '\u7956': 'To', '\u4f20': 'Truyen', '\u627f': 'Thua',
    '\u524d': 'Tien', '\u8f88': 'Boi', '\u6666': 'Van',
    '\u51f0': 'Phuong',
}


def han_viet_name(cn_text: str) -> str:
    """Convert a Chinese name/term to Hán-Việt, title-cased."""
    parts = []
    for ch in cn_text:
        if ch in HAN_VIET:
            parts.append(HAN_VIET[ch])
        elif '\u4e00' <= ch <= '\u9fff':
            parts.append(ch)
    if not parts:
        return cn_text
    return ' '.join(p.capitalize() for p in parts)


SINGLE_SURNAMES: set = set(
    '\u674e\u738b\u5f20\u5218\u9648\u6768\u8d75\u9ec4\u5468\u5434\u5f90\u5b59\u80e1\u6731\u9ad8'
    '\u6797\u4f55\u90ed\u9a6c\u7f57\u6881\u5b8b\u90d1\u8c22\u97e9\u5510\u51af\u4e8e\u8463\u8427'
    '\u7a0b\u66f9\u8881\u9093\u8bb8\u5085\u6c88\u66fe\u5f6d\u5415\u82cf\u5362\u848b\u8521\u8d3e'
    '\u4e01\u9b4f\u8585\u53f6\u960e\u4f59\u6f58\u675c\u6234\u590f\u9492\u6c6a\u7530\u4efb\u59dc'
    '\u8303\u65b9\u77f3\u59da\u8c2d\u5ed6\u90b9\u718a\u91d1\u9646\u90dd\u5b54\u767d\u5d14\u5eb7'
    '\u6bdb\u90b1\u79e6\u6c5f\u53f2\u987e\u4faf\u90b5\u5b5f\u9f99\u4e07\u6bb5\u96f7\u9322\u6c64'
    '\u5c39\u9ece\u5e38\u6b66\u8d3a\u8d96\u9f9a\u6587\u4e54\u6b27\u5b81\u8300\u90a2\u962e\u97e6'
)

DOUBLE_SURNAMES: list = [
    '\u6b27\u9633', '\u53f8\u9a6c', '\u4e0a\u5b98', '\u8bf8\u845b', '\u4e1c\u65b9',
    '\u72ec\u5b64', '\u5357\u5bab', '\u6155\u5bb9', '\u897f\u95e8', '\u957f\u5b59',
    '\u8f69\u8f95', '\u4ee4\u72d0', '\u5c09\u8fdf', '\u7687\u752b', '\u590f\u4faf',
    '\u516c\u5b59', '\u7533\u5c60', '\u767e\u91cc', '\u516c\u7f8a', '\u7f8a\u820c',
    '\u5fae\u751f', '\u8d3a\u5170', '\u8d6b\u8fde', '\u547c\u5ef6', '\u4e07\u4fc3',
    '\u62d3\u8dc4',
]

CONTEXT_PATTERNS: list = [
    r'(.{1,4})(?:\u8bf4\u9053|\u7b11\u9053|\u51b7\u58f0\u9053|\u6c89\u58f0\u9053|\u4f4e\u58f0\u9053)',
    r'(.{1,4})(?:\u95ee\u9053|\u8ffd\u95ee|\u8d28\u95ee)',
    r'(.{1,4})(?:\u770b\u7740|\u671b\u7740|\u6ce8\u89c6\u7740|\u76ef\u7740|\u51dd\u89c6\u7740)',
    r'(.{1,4})(?:\u76b1\u7709|\u70b9\u5934|\u6447\u5934|\u82e6\u7b11|\u51b7\u7b11|\u5fae\u7b11)',
    r'(.{1,4})(?:\u51fa\u624b|\u51fa\u62db|\u52a8\u624b|\u6325\u5251|\u8fd0\u529f)',
    r'(.{1,4})(?:\u5e08\u5144|\u5e08\u59d0|\u5e08\u5f1f|\u5e08\u59b9|\u5e08\u7236|\u5e08\u5c0a)',
    r'(.{1,4})(?:\u957f\u8001|\u516c\u5b50|\u5c0f\u59d0|\u59d1\u5a18|\u5927\u4eba|\u524d\u8f88)',
    r'(.{1,4})(?:\u5b97\u4e3b|\u95e8\u4e3b|\u638c\u95e8|\u5802\u4e3b|\u5ea7\u4e3b|\u6559\u4e3b)',
    r'(.{1,4})(?:\u9648\u4e0b|\u6bbf\u4e0b|\u9601\u4e0b)',
    r'(.{1,4})(?:\u7684\u58f0\u97f3|\u7684\u76ee\u5149|\u7684\u8eab\u5f71|\u7684\u6c14\u606f)',
]

STOPWORD_TERMS: set = {
    '\u4ec0\u4e48', '\u8fd9\u4e2a', '\u90a3\u4e2a', '\u4e00\u4e2a', '\u4ed6\u4eec',
    '\u5979\u4eec', '\u6211\u4eec', '\u4f60\u4eec', '\u6ca1\u6709', '\u53ef\u4ee5',
    '\u4e0d\u662f', '\u8fd8\u662f', '\u5c31\u662f', '\u5982\u679c', '\u867d\u7136',
    '\u4f46\u662f', '\u7136\u540e', '\u56e0\u4e3a', '\u6240\u4ee5', '\u5df2\u7ecf',
    '\u4e0d\u8fc7', '\u800c\u4e14', '\u6216\u8005', '\u8fd8\u6709', '\u975e\u5e38',
    '\u5341\u5206', '\u771f\u7684', '\u4e00\u5b9a', '\u53ef\u80fd', '\u5e94\u8be5',
    '\u9700\u8981', '\u77e5\u9053', '\u89c9\u5f97', '\u611f\u89c9', '\u770b\u5230',
    '\u542c\u5230', '\u8bf4\u9053', '\u95ee\u9053', '\u7b11\u9053', '\u60f3\u5230',
    '\u5fc3\u4e2d', '\u773c\u4e2d', '\u624b\u4e2d', '\u4f53\u5185', '\u5929\u7a7a',
    '\u5730\u9762', '\u56db\u5468', '\u5468\u56f4', '\u7a81\u7136', '\u5ffd\u7136',
    '\u968f\u5373', '\u987f\u65f6', '\u77ac\u95f4', '\u7247\u523b', '\u6b64\u65f6',
    '\u53ea\u89c1', '\u5374\u89c1', '\u4f46\u89c1', '\u53ea\u662f', '\u4e0d\u7981',
    '\u7adf\u7136', '\u5c45\u7136', '\u679c\u7136',
}

ENTITY_SUFFIXES: dict = {
    '\u5b97': 'SECT', '\u95e8': 'SECT', '\u6d3e': 'SECT', '\u6559': 'SECT', '\u6bbf': 'SECT',
    '\u9601': 'SECT', '\u5802': 'SECT', '\u5e84': 'SECT', '\u5d6e': 'SECT', '\u697c': 'SECT',
    '\u5cf0': 'PLACE', '\u5c9b': 'PLACE', '\u57ce': 'PLACE', '\u56fd': 'PLACE', '\u754c': 'PLACE',
    '\u57df': 'PLACE', '\u6d77': 'PLACE', '\u5c71': 'PLACE', '\u6e56': 'PLACE', '\u6cb3': 'PLACE',
    '\u5cb3': 'PLACE', '\u6d32': 'PLACE', '\u6e0a': 'PLACE', '\u6797': 'PLACE', '\u8c37': 'PLACE',
    '\u8bc0': 'SKILL', '\u529f': 'SKILL', '\u6cd5': 'SKILL', '\u672f': 'SKILL', '\u7ecf': 'SKILL',
    '\u638c': 'SKILL', '\u5251': 'SKILL', '\u5200': 'SKILL', '\u62f3': 'SKILL', '\u817f': 'SKILL',
    '\u4e39': 'ITEM', '\u836f': 'ITEM', '\u5b9d': 'ITEM', '\u5668': 'ITEM', '\u7b26': 'ITEM',
    '\u73e0': 'ITEM', '\u73af': 'ITEM', '\u955c': 'ITEM', '\u5854': 'ITEM', '\u9f0e': 'ITEM',
}
