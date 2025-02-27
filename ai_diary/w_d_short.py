import pandas as pd
from flask import Flask, request, jsonify
from openai import OpenAI
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

# .env 강제 로드
load_dotenv(override=True)

# Flask 앱 생성
app = Flask(__name__)

# 환경 변수에서 API 키 가져오기
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# DB 연결 설정
DATABASE_URL = "mysql+pymysql://yeonju:password@34.64.119.157/golmok"
engine = create_engine(DATABASE_URL, echo=True)

# SQL 쿼리 딕셔너리
queries = {
    "user": "SELECT * FROM user",
    "trip": "SELECT * FROM trip",
    "place": "SELECT * FROM place",
    "map_pin": "SELECT * FROM map_pin",
}

# 데이터 가져오기 (Pandas DataFrame 변환)
with engine.connect() as conn:
    user_data = pd.read_sql_query(queries["user"], conn)
    trip_data = pd.read_sql_query(queries["trip"], conn)
    place_data = pd.read_sql_query(queries["place"], conn)
    map_pin_data = pd.read_sql_query(queries["map_pin"], conn)

# 날짜 데이터 변환 (존재하는 컬럼만 변환)
date_columns = {
    "trip": ["start_date", "end_date"],
}

for table, columns in date_columns.items():
    for col in columns:
        if col in locals()[f"{table}_data"].columns:
            locals()[f"{table}_data"][col] = pd.to_datetime(locals()[f"{table}_data"][col], errors="coerce")

# 데이터 병합
pin_trip_data = pd.merge(trip_data, map_pin_data, on="trip_id", how="left")  # MapPin + 여행 기록
place_trip_data = pd.merge(pin_trip_data, place_data, on="place_name", how="left")  # MapPin + 장소 데이터 + 여행 기록

# keyword_data 생성
keyword_data = place_trip_data[["title", "start_date", "end_date", "place_name", "type"]].copy()

keyword_data["start_date"] = keyword_data["start_date"].dt.date
keyword_data["end_date"] = keyword_data["end_date"].dt.date


# 추천 일기 생성 API
@app.route('/diary', methods=['GET'])
def recommend_diary():
    try:
        # 사용자 요청에서 날짜를 가져옵니다.
        selected_date = request.args.get('selected_date')  # 선택한 날짜 (yyyy-mm-dd)
        user_id = request.args.get('user_id')  # 사용자 ID
        
        if not selected_date:
            return jsonify({"error": "날짜를 선택해 주세요."}), 400
        if not user_id:
            return jsonify({"error": "user_id가 필요합니다."}), 400
        
        # user_id를 정수형으로 변환 (예외 처리)
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({"error": "user_id는 숫자여야 합니다."}), 400

        # 'selected_date'를 datetime 객체로 변환
        selected_date = pd.to_datetime(selected_date).date()

        # 유저 ID로 여행 데이터 필터링
        user_trips = trip_data[trip_data["user_id"] == user_id]

        if user_trips.empty:
            return jsonify({"error": "해당 user_id에 대한 여행 기록이 없습니다."}), 400

        # 여행 기록이 있는 user_id에 대해 keyword_data 필터링
        filtered_data = keyword_data[
            (keyword_data["start_date"] <= selected_date) &
            (keyword_data["end_date"] >= selected_date) &
            (keyword_data["title"].isin(user_trips["title"]))  # 해당 유저의 여행 기록만 필터링
        ]

        if filtered_data.empty:
            return jsonify({"error": "선택한 날짜에 대한 장소 정보가 없습니다."}), 400

        # 선택된 날짜에 해당하는 장소 이름과 타입을 키워드로 생성
        keywords = [f"{row['place_name']} ({row['type']})" for _, row in filtered_data.iterrows()]

        # OpenAI 프롬프트 설정
        today = pd.to_datetime("today").strftime("%Y-%m-%d")
        prompt = f"""
        오늘({today}) 하루 동안 있었던 일을 바탕으로 짧고 간결한 일기를 작성해줘.
        핵심만 요약해서 자연스럽게 마무리되는 감성적인 일기를 3~4문장으로 작성해줘.
        여기 있는 키워드를 바탕으로 일기를 작성해줘: {', '.join(keywords)}
        """

        # OpenAI API 호출
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}],
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=200
            )
            diary_entry_content = chat_completion.choices[0].message.content.strip()
        except Exception as e:
            return jsonify({"error": "OpenAI API 호출 실패", "details": str(e)}), 500

        # API 응답
        return jsonify({
            "diary_date": today,
            "user_id": user_id,
            "keywords": keywords,
            "ai_draft": diary_entry_content
        }), 200, {"Content-Type": "application/json; charset=utf-8"}

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Flask 서버 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
