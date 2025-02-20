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

# 데이터베이스에서 여행 정보 가져오기
def get_trip_info(tripid):
    conn = sqlite3.connect("demoDB.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT title, startDate, endDate FROM Trip WHERE id = ?", (tripid,))
    result = cursor.fetchone()
    
    conn.close()
    return result if result else ("알 수 없는 여행", "날짜 없음", "날짜 없음")

# 데이터베이스에서 장소 정보 가져오기
def get_place_info(place_name):
    conn = sqlite3.connect("demoDB.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT type FROM Place WHERE placeName = ?", (place_name,))
    result = cursor.fetchone()
    
    conn.close()
    return (place_name, result[0]) if result else (place_name, "일반적인 장소")

# 추천 일기 생성 API
@app.route('/recommend', methods=['GET'])
def recommend_diary():
    try:
        # 요청 파라미터 가져오기
        tripid = request.args.get('tripid', type=int)
        place = request.args.get('place', type=str)

        if not tripid or not place:
            return jsonify({"error": "tripid와 place를 모두 제공해야 합니다."}), 400

        # 날짜 가져오기
        today = datetime.date.today().strftime("%Y-%m-%d")

        # 여행 정보 가져오기
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
            messages=[
                {"role": "system", "content": "너는 친절한 일기 작가야. 간결하고 자연스러운 문장을 사용해."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=150
        )

        # 응답 저장
        diary_entry = chat_completion.choices[0].message.content.strip()

        # 결과 반환
        return jsonify({
            "date": today,
            "tripTitle": trip_title,
            "tripPeriod": f"{trip_start} ~ {trip_end}",
            "place": selected_place,
            "placeType": place_type,
            "diaryEntry": diary_entry
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Flask 서버 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
