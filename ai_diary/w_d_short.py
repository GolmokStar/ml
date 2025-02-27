import os
import datetime
import sqlite3
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# .env 강제 로드
load_dotenv(override=True)

# Flask 앱 생성
app = Flask(__name__)

# 환경 변수에서 API 키 가져오기
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# 데이터베이스 연결 함수
def get_db_connection():
    conn = sqlite3.connect("demoDB.db")
    conn.row_factory = sqlite3.Row
    return conn

# 여행 정보 가져오기
def get_trip_info(tripid):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT title, startDate, endDate FROM Trip WHERE id = ?", (tripid,))
    result = cursor.fetchone()
    
    conn.close()
    return result if result else ("알 수 없는 여행", "날짜 없음", "날짜 없음")

# 장소 정보 가져오기
def get_place_info(place_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT type FROM Place WHERE placeName = ?", (place_name,))
    result = cursor.fetchone()
    
    conn.close()
    return (place_name, result[0]) if result else (place_name, "일반적인 장소")

# 추천 일기 생성 API
@app.route('/recommend', methods=['GET'])
def recommend_diary():
    try:
        tripid = request.args.get('tripid', type=int)
        place = request.args.get('place', type=str)

        if not tripid or not place:
            return jsonify({"error": "tripid와 place를 모두 제공해야 합니다."}), 400

        today = datetime.date.today().strftime("%Y-%m-%d")
        trip_title, trip_start, trip_end = get_trip_info(tripid)
        selected_place, place_type = get_place_info(place)

        # ChatGPT 프롬프트 설정
        prompt = f"""
        오늘({today}) 하루 동안 있었던 일을 바탕으로 짧고 간결한 일기를 작성해줘.
        이번 여행의 제목은 '{trip_title}'이고, 여행 기간은 {trip_start}부터 {trip_end}까지야.
        오늘은 '{selected_place}'을(를) 방문했어. 이곳은 '{place_type}'과 관련된 곳이야.
        핵심만 요약해서 자연스럽게 마무리되는 감성적인 일기를 3~4문장으로 작성해줘.
        """

        # OpenAI API 호출
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": "너는 친절한 일기 작가야. 간결하고 자연스러운 문장을 사용해."},
                      {"role": "user", "content": prompt}],
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=150
        )

        diary_entry = chat_completion.choices[0].message.content.strip()

        # 데이터베이스에 저장 (aiDraft 칼럼에 일기 내용 저장)
        conn = get_db_connection()
        cursor = conn.cursor()

        # tripid가 이미 존재하는지 확인
        cursor.execute("SELECT * FROM Diary WHERE tripid = ?", (tripid,))
        existing_entry = cursor.fetchone()

        if existing_entry:
            # 존재하면 업데이트
            cursor.execute(
                "UPDATE Diary SET aiDraft = ? WHERE tripid = ?",
                (diary_entry, tripid)
            )
        else:
            # 존재하지 않으면 삽입
            cursor.execute(
                "INSERT INTO Diary (tripid, date, place, aiDraft) VALUES (?, ?, ?, ?)",
                (tripid, today, selected_place, diary_entry)
            )

        conn.commit()
        conn.close()

        return jsonify({
            "date": today,
            "tripTitle": trip_title,
            "tripPeriod": f"{trip_start} ~ {trip_end}",
            "place": selected_place,
            "placeType": place_type,
            "aiDraft": diary_entry  # aiDraft를 반환
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Flask 서버 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
