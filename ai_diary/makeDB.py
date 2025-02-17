import sqlite3

# 데이터베이스 연결 (없으면 새로 생성됨)
conn = sqlite3.connect("demoDB.db")
cursor = conn.cursor()

# Trip 테이블 생성
cursor.execute("""
CREATE TABLE IF NOT EXISTS Trip (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    startDate TEXT NOT NULL,
    endDate TEXT NOT NULL
);
""")

# Place 테이블 생성
cursor.execute("""
CREATE TABLE IF NOT EXISTS Place (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placeName TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL
);
""")

# Diary 테이블 생성
cursor.execute("""
CREATE TABLE IF NOT EXISTS Diary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tripid INTEGER NOT NULL,
    entryDate TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (tripid) REFERENCES Trip (id)
);
""")

# 샘플 데이터 삽입
try:
    cursor.executemany("""
    INSERT INTO Trip (title, startDate, endDate) VALUES (?, ?, ?);
    """, [
        ('전주 여행', '2024-02-10', '2024-02-15'),
        ('부산 맛집 투어', '2024-03-05', '2024-03-10')
    ])

    cursor.executemany("""
    INSERT INTO Place (placeName, type) VALUES (?, ?);
    """, [
        ('전주 한옥마을', '전통 문화'),
        ('감천 문화마을', '예술과 감성'),
        ('해운대', '해변과 바다')
    ])

    cursor.executemany("""
    INSERT INTO Diary (tripid, entryDate, content) VALUES (?, ?, ?);
    """, [
        (1, '2024-02-11', '전주 한옥마을에서 한복을 입고 사진을 찍었다.')
    ])

except sqlite3.IntegrityError:
    print("⚠️ 일부 데이터가 이미 존재하여 삽입되지 않았습니다.")

# 변경 사항 저장 후 연결 종료
conn.commit()
conn.close()

print("테스트용 diary.db 파일이 생성되었으며, 기본 데이터가 추가되었습니다!")
