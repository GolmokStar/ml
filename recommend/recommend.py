from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify
from sklearn.metrics.pairwise import cosine_similarity

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import traceback
import json

app = Flask(__name__)

# DB 연결 설정
DATABASE_URL = "mysql+pymysql://yeonju:password@34.64.119.157/golmok"
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)

# SQL 쿼리 딕셔너리
queries = {
    "user": "SELECT * FROM user",
    "interest": "SELECT * FROM interest_area",
    "trip": "SELECT * FROM trip",
    "place": "SELECT * FROM place",
    "map_pin": "SELECT * FROM map_pin",
    "record": "SELECT * FROM record",
}

# 데이터 가져오기 (Pandas DataFrame 변환)
with engine.connect() as conn:
    user_data = pd.read_sql_query(queries["user"], conn)
    interest_data = pd.read_sql_query(queries["interest"], conn)
    trip_data = pd.read_sql_query(queries["trip"], conn)
    place_data = pd.read_sql_query(queries["place"], conn)
    map_pin_data = pd.read_sql_query(queries["map_pin"], conn)
    record_data = pd.read_sql_query(queries["record"], conn)

# 날짜 데이터 변환 (존재하는 컬럼만 변환)
date_columns = {
    "user": ["birth_date"],
    "trip": ["start_date", "end_date"],
    "record": ["visit_date"],
}

for table, columns in date_columns.items():
    for col in columns:
        if col in locals()[f"{table}_data"].columns:
            locals()[f"{table}_data"][col] = pd.to_datetime(locals()[f"{table}_data"][col], errors="coerce")

# 데이터 병합
user_interest_data = pd.merge(user_data, interest_data, on="user_id", how="left")  # 사용자 정보 + 관심사
user_trip_data = pd.merge(user_data, trip_data, on="user_id", how="left")  # 사용자 정보 + 여행 기록
trip_place_data = pd.merge(map_pin_data, place_data, on="place_name", how="left")  # MapPin + 장소 데이터
trip_place_record_data = pd.merge(trip_place_data, record_data, on="pin_id", how="left")  # 여행 장소 + 방문 기록
record_with_place = pd.merge(record_data, map_pin_data[["pin_id", "place_name"]], on="pin_id", how="left")  # 기록하기 + placeId
user_place_record_data = pd.merge(user_interest_data, trip_place_record_data, on="user_id", how="left")  # 최종 병합

# Google Places API type과 InterestArea.interest 매핑
type_to_interest = {
    "food": ["bakery", "bar", "cafe", "meal_delivery", "meal_takeaway", "restaurant"],
    "activities": ["amusement_park", "aquarium", "bowling_alley", "campground", "casino", "gym", "movie_theater", "night_club", "stadium", "zoo", "rv_park"],
    "culture_arts": ["art_gallery", "book_store", "library", "museum", "hindu_temple", "mosque", "church", "synagogue"],
    "healing": ["spa"],
    "nature": ["park", "tourist_attraction"],
    "shopping": ["clothing_store", "department_store", "electronics_store", "florist", "furniture_store", "hardware_store", "home_goods_store", "jewelry_store", "shoe_store", "shopping_mall", "store", "supermarket", "convenience_store", "liquor_store"]
}

# 사용자 관심 분야 매핑
def map_place_to_interest(place_type):
    for interest, types in type_to_interest.items():
        if place_type in types:
            return interest
    return "etc"

user_place_record_data["interestCategory"] = place_data["type"].apply(map_place_to_interest)


# 사용자 연령대 계산
current_year = datetime.now().year
user_data["birth_date"] = pd.to_datetime(user_data["birth_date"], errors="coerce")
user_data["age"] = (current_year - user_data["birth_date"].dt.year).fillna(0).astype(int)
user_data["age_group"] = user_data["age"].apply(lambda x: "Teenagers" if x < 20 else "Adults")


############################
######## 장소 추천 ##########
############################

def recommend_places(user_id):
    session = Session()

    user = user_data[user_data["user_id"] == user_id].iloc[0]
    user_age_group = user["age_group"]
    user_interest = interest_data[interest_data["user_id"] == user_id]["interest"].tolist()
    
    # (1) 새로운 테이블 생성
    place_scores = place_data[["place_name", "latitude", "longitude", "type"]].copy()
    
    # (2) 사용자가 방문한 장소 유형 확인
    visited_places = user_place_record_data[user_place_record_data["user_id"] == user_id]
    visited_types = visited_places["type"].value_counts(normalize=True)

    # (3) One-Hot Encoding 후 코사인 유사도 계산
    if visited_types.empty:
        place_scores["similarity"] = 0  # 기본 유사도 0으로 설정
    else:
        place_types = pd.get_dummies(place_scores["type"])
        visited_vector = visited_types.reindex(place_types.columns, fill_value=0).values.reshape(1, -1)
        place_vectors = place_types.values

        similarity_scores = cosine_similarity(visited_vector, place_vectors)[0]
        place_scores["similarity"] = similarity_scores


    # (4) 별점 가중치 추가
    avg_ratings = record_with_place.groupby("place_name")["rating"].mean().reset_index()
    place_scores = pd.merge(place_scores, avg_ratings, on="place_name", how="left").fillna(0)
    place_scores["score"] = place_scores["similarity"] * 0.5 + place_scores["rating"] * 0.5

    # (5) 같은 연령대 방문 장소 반영
    similar_age_users = user_data[user_data["age_group"] == user_age_group]["user_id"].tolist()
    similar_age_trips = user_trip_data[user_trip_data["user_id"].isin(similar_age_users)]
    similar_age_places = pd.merge(similar_age_trips, map_pin_data, on="trip_id", how="left")
    popular_places_by_age = similar_age_places["place_name"].value_counts().to_dict()

    place_scores["age_weight"] = place_scores["place_name"].map(lambda x: popular_places_by_age.get(x, 0))
    place_scores["score"] += place_scores["age_weight"] * 0.2

    # (6) 사용자의 관심 카테고리 반영
    place_scores["interest_weight"] = user_place_record_data["interest"].apply(lambda x: 1 if x in user_interest else 0)
    place_scores["score"] += place_scores["interest_weight"] * 0.3

    # (7) 계절별 가중치 반영
    current_month = datetime.now().month
    season = (
        "Winter" if current_month in [12, 1, 2] else
        "Spring" if current_month in [3, 4, 5] else
        "Summer" if current_month in [6, 7, 8] else
        "Fall"
    )

    trip_data["start_date"] = pd.to_datetime(trip_data["start_date"])
    popular_places_by_season = trip_data[trip_data["start_date"].dt.month == current_month]["trip_id"].value_counts()
    place_scores["season_weight"] = place_scores["place_name"].apply(lambda x: popular_places_by_season.get(x, 0))
    place_scores["score"] += place_scores["season_weight"] * 0.2

    # (8) 협업 필터링 - 유사한 사용자들의 방문 데이터 활용
    user_place_matrix = user_place_record_data.pivot_table(index="user_id", columns="place_name", values="rating").fillna(0)

    if user_id in user_place_matrix.index:
        user_vector = user_place_matrix.loc[user_id].values.reshape(1, -1)
        user_similarities = cosine_similarity(user_vector, user_place_matrix.values)[0]
        user_place_matrix["similarity"] = user_similarities
        similar_users = user_place_matrix.sort_values("similarity", ascending=False).iloc[1:6]

        similar_users_places = similar_users.drop(columns=["similarity"]).mean().to_dict()
        place_scores["collaborative_weight"] = place_scores["place_name"].map(lambda x: similar_users_places.get(x, 0))
        place_scores["score"] += place_scores["collaborative_weight"] * 0.3

    # (9) 추천 장소 선정 (상위 5개)
    recommended_places = place_scores.sort_values("score", ascending=False).head(5)

    try:
        delete_query = text("DELETE FROM recommendation WHERE user_id = :user_id")
        session.execute(delete_query, {"user_id": user_id})

        # 새로운 추천 삽입 (executemany 사용)
        insert_query = text("""
            INSERT INTO recommendation (age_group, ranking, season, type, user_id)
            VALUES (:age_group, :ranking, :season, :type, :user_id)
        """)

        data_to_insert = [
            {
                "age_group": user_age_group, 
                "ranking": rank + 1, 
                "season": season, 
                "type": row["type"], 
                "user_id": user_id
            }
            for rank, row in enumerate(recommended_places.to_dict(orient="records"))
        ]

        if data_to_insert:  # 추천 데이터가 존재할 때만 실행
            session.execute(insert_query, data_to_insert)  # executemany 방식!

        session.commit()  # 변경사항 저장
    except Exception as e:
        session.rollback()  # 오류 발생 시 롤백
        print("DB 업데이트 중 오류 발생:", e)
    finally:
        session.close()  # 세션 종료

        return recommended_places[["place_name", "latitude", "longitude"]].reset_index(drop=True)

@app.route('/recommend', methods=['GET'])
def get_recommendations():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    recommendations = recommend_places(user_id)
    
    return app.response_class(
        response=json.dumps(recommendations.to_dict(orient="records"), ensure_ascii=False, indent=2),
        status=200,
        mimetype="application/json"
    )

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)