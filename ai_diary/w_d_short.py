import os
import datetime
import sqlite3
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
import requests

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

# 추천 일기 생성 API
@app.route('/recommend', methods=['GET'])
def recommend_diary():
    try:
        tripid = request.args.get('tripid', type=int)
        if tripid is None or tripid <= 0:
            return jsonify({"error": "유효한 tripid를 제공해야 합니다."}), 400

        today = datetime.date.today().strftime("%Y-%m-%d")

        # ChatGPT 프롬프트 설정
        prompt = f"""
        오늘({today}) 하루 동안 있었던 일을 바탕으로 짧고 간결한 일기를 작성해줘.
        핵심만 요약해서 자연스럽게 마무리되는 감성적인 일기를 3~4문장으로 작성해줘.
        """

        # OpenAI API 호출
        try:
            chat_completion = client.chat.completions.create(
                messages=[ ... ],
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=150
            )
            diary_entry = chat_completion.choices[0].message.content.strip()
        except Exception as e:
            return jsonify({"error": "OpenAI API 호출 실패", "details": str(e)}), 500

        # API 전송
        data = {
            "tripId": tripid,
            "diaryDate": today,
            "aiDraft": diary_entry
        }

        api_url = os.getenv("EXTERNAL_API_URL")

        try:
            response = requests.post(api_url, json=data, timeout=5)  # 5초 제한
            response.raise_for_status()  # HTTP 오류 발생 시 예외 처리
        except requests.exceptions.Timeout:
            return jsonify({"error": "AI 일기 전송 실패", "details": "요청 시간이 초과되었습니다."}), 500
        except requests.exceptions.RequestException as e:
            return jsonify({"error": "AI 일기 전송 실패", "details": str(e)}), 500

        return jsonify({
            "diaryDate": today,
            "tripId": tripid,
            "aiDraft": diary_entry
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Flask 서버 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
