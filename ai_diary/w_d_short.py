import os
import datetime
import sqlite3
from dotenv import load_dotenv
from openai import OpenAI

# .env 강제 로드
load_dotenv(override=True)

# 환경 변수에서 API 키 가져오기
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# 오늘 날짜 가져오기
today = datetime.date.today().strftime("%Y-%m-%d")

# 사용자가 선택한 일기의 tripid 및 장소
user_selected_tripid = 1  # 예제 값 (앱에서 전달되는 값으로 변경)
user_selected_place = "전주 한옥마을"  # 예제 값 (앱에서 전달되는 값으로 변경)

# 데이터베이스에서 여행 및 장소 정보 가져오기
def get_trip_info(tripid):
    conn = sqlite3.connect("demoDB.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT title, startDate, endDate FROM Trip WHERE id = ?", (tripid,))
    result = cursor.fetchone()
    
    conn.close()
    return result if result else ("알 수 없는 여행", "날짜 없음", "날짜 없음")

def get_place_info(place_name):
    conn = sqlite3.connect("demoDB.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT type FROM Place WHERE placeName = ?", (place_name,))
    result = cursor.fetchone()
    
    conn.close()
    return (place_name, result[0]) if result else (place_name, "일반적인 장소")

# Trip 및 Place 정보 가져오기
trip_title, trip_start, trip_end = get_trip_info(user_selected_tripid)
selected_place, place_type = get_place_info(user_selected_place)

# ChatGPT 프롬프트 설정 (간결한 문장 요청)
prompt = f"""
오늘({today}) 하루 동안 있었던 일을 바탕으로 짧고 간결한 일기를 작성해줘.
이번 여행의 제목은 '{trip_title}'이고, 여행 기간은 {trip_start}부터 {trip_end}까지야.
오늘은 '{selected_place}'을(를) 방문했어. 이곳은 '{place_type}'과 관련된 곳이야.
핵심만 요약해서 자연스럽게 마무리되는 감성적인 일기를 3~4문장으로 작성해줘.
"""

# ChatGPT API 요청 (짧은 출력 설정)
chat_completion = client.chat.completions.create(
    messages=[
        {"role": "system", "content": "너는 친절한 일기 작가야. 간결하고 자연스러운 문장을 사용해."},
        {"role": "user", "content": prompt}
    ],
    model="gpt-3.5-turbo",
    temperature=0.7,
    max_tokens=150  # 조금 여유롭게 조정
)

# 응답 저장
diary_entry = chat_completion.choices[0].message.content.strip()

# 결과 출력
print(f"오늘의 일기:\n{diary_entry}")

# 파일로 저장 (선택 사항)
file_path = f"diary_{today}.txt"
with open(file_path, "w", encoding="utf-8") as file:
    file.write(diary_entry)

print(f"일기가 {file_path} 파일로 저장되었습니다.")
