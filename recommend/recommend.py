from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify
from sklearn.metrics.pairwise import cosine_similarity

import pymysql

app = Flask(__name__)

conn = pymysql.connect(host='00.00.000.000',
                        user='abc',
                        password='password',
                        db='hello',
                        port=3306,
                        cursorclass=pymysql.cursors.DictCursor
                        )

cursor = conn.cursor()

# SQL 쿼리 작성
user_query = "SELECT * FROM User"
interest_query = "SELECT * FROM InterestArea"
trip_query = "SELECT * FROM Trip"
place_query = "SELECT * FROM Place"
map_pin_query = "SELECT * FROM MapPin"
record_query = "SELECT * FROM Record"

# 데이터 가져오기 (Pandas DataFrame 변환)
user_data = pd.read_sql_query(user_query, conn)
interest_data = pd.read_sql_query(interest_query, conn)
trip_data = pd.read_sql_query(trip_query, conn)
place_data = pd.read_sql_query(place_query, conn)
map_pin_data = pd.read_sql_query(map_pin_query, conn)
record_data = pd.read_sql_query(record_query, conn)


# 데이터 병합
user_interest_data = pd.merge(user_data, interest_data, on="userId", how="left")  # 사용자 정보 + 관심사
user_trip_data = pd.merge(user_data, trip_data, on="userId", how="left")  # 사용자 정보 + 여행 기록
trip_place_data = pd.merge(map_pin_data, place_data, on="placeId", how="left")  # MapPin + 장소 데이터
trip_place_record_data = pd.merge(trip_place_data, record_data, on="pinId", how="left")  # 여행 장소 + 방문 기록
record_with_place = pd.merge(record_data, map_pin_data[["pinId", "placeId"]], on="pinId", how="left") # 기록하기 + placeId
user_place_record_data = pd.merge(user_interest_data, trip_place_record_data, on="userId", how="left")  # 최종 병합

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

place_data["interestCategory"] = place_data["type"].apply(map_place_to_interest)


# 사용자 연령대 계산
current_year = datetime.now().year
user_data["birthDate"] = pd.to_datetime(user_data["birthDate"])
user_data["age"] = current_year - user_data["birthDate"].dt.year
user_data["ageGroup"] = user_data["age"].apply(lambda x: "Teenagers" if x < 20 else "Adults")


def recommend_places(user_id):
    user = user_data[user_data["userId"] == user_id].iloc[0]
    user_age_group = user["ageGroup"]
    user_interest = interest_data[interest_data["userId"] == user_id]["interest"].tolist()
    
    # (1) 새로운 테이블 생성
    place_scores = place_data[["placeId", "placeName", "latitude", "longitude", "type"]].copy()
    
    # (2) 사용자가 방문한 장소 유형 확인
    visited_places = user_place_record_data[user_place_record_data["userId"] == user_id]
    visited_types = visited_places["type"].value_counts(normalize=True)

    # (3) One-Hot Encoding 후 코사인 유사도 계산
    place_types = pd.get_dummies(place_scores["type"])  # One-Hot Encoding
    visited_vector = visited_types.reindex(place_types.columns, fill_value=0).values.reshape(1, -1)
    place_vectors = place_types.values
    
    similarity_scores = cosine_similarity(visited_vector, place_vectors)[0]
    place_scores["similarity"] = similarity_scores  # 새로운 테이블에 유사도 추가

    # (4) 별점 가중치 추가
    avg_ratings = record_with_place.groupby("placeId")["rating"].mean().reset_index()
    place_scores = pd.merge(place_scores, avg_ratings, on="placeId", how="left").fillna(0)
    place_scores["score"] = place_scores["similarity"] * 0.5 + place_scores["rating"] * 0.5

    # (5) 같은 연령대 방문 장소 반영
    similar_age_users = user_data[user_data["ageGroup"] == user_age_group]["userId"].tolist()
    similar_age_trips = user_trip_data[user_trip_data["userId"].isin(similar_age_users)]
    similar_age_places = pd.merge(similar_age_trips, map_pin_data, on="tripId", how="left")
    popular_places_by_age = similar_age_places["placeId"].value_counts().to_dict()

    place_scores["age_weight"] = place_scores["placeId"].map(lambda x: popular_places_by_age.get(x, 0))
    place_scores["score"] += place_scores["age_weight"] * 0.2

    # (6) 사용자의 관심 카테고리 반영
    place_scores["interest_weight"] = user_place_record_data["interestCategory"].apply(lambda x: 1 if x in user_interest else 0)
    place_scores["score"] += place_scores["interest_weight"] * 0.3

    # (7) 계절별 가중치 반영
    current_month = datetime.now().month
    season = (
        "Winter" if current_month in [12, 1, 2] else
        "Spring" if current_month in [3, 4, 5] else
        "Summer" if current_month in [6, 7, 8] else
        "Fall"
    )
    trip_data["startDate"] = pd.to_datetime(trip_data["startDate"])
    popular_places_by_season = trip_data[trip_data["startDate"].dt.month == current_month]["tripId"].value_counts()
    place_scores["season_weight"] = place_scores["placeId"].apply(lambda x: popular_places_by_season.get(x, 0))
    place_scores["score"] += place_scores["season_weight"] * 0.2

    # (8) 협업 필터링 - 유사한 사용자들의 방문 데이터 활용
    user_place_matrix = record_with_place.pivot_table(index="userId", columns="placeId", values="rating").fillna(0)

    if user_id in user_place_matrix.index:
        user_vector = user_place_matrix.loc[user_id].values.reshape(1, -1)
        user_similarities = cosine_similarity(user_vector, user_place_matrix.values)[0]
        user_place_matrix["similarity"] = user_similarities
        similar_users = user_place_matrix.sort_values("similarity", ascending=False).iloc[1:6]

        similar_users_places = similar_users.drop(columns=["similarity"]).mean().to_dict()
        place_scores["collaborative_weight"] = place_scores["placeId"].map(lambda x: similar_users_places.get(x, 0))
        place_scores["score"] += place_scores["collaborative_weight"] * 0.3

    # (9) 추천 장소 선정 (상위 5개)
    recommended_places = place_scores.sort_values("score", ascending=False).head(5)

    

    recommendation_df = pd.DataFrame({
        "placeId": recommended_places["placeId"].values,
        "type": recommended_places["type"].values,
        "season": season,
        "ageGroup": user_age_group,
        "ranking": range(1, len(recommended_places) + 1)
    })
    
    #print("\n=== 추천 테이블 (recommendation_df) ===")
    #print(recommendation_df)

    # (10) MySQL에 저장 (기존 데이터 삭제 후 삽입)
    with conn.cursor() as cursor:
        trans = conn.begin()
        try:
            # 기존 추천 삭제
            delete_query = "DELETE FROM recommendation WHERE userId = %s"
            cursor.execute(delete_query, (user_id,))

            # 새로운 추천 삽입
            insert_query = """
            INSERT INTO recommendation (userId, placeId, type, season, ageGroup, ranking)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            data_to_insert = [
                (user_id, row["placeId"], row["type"], season, user_age_group, rank)
                for rank, row in recommended_places.iterrows()
            ]
            cursor.executemany(insert_query, data_to_insert)

            trans.commit()
        except Exception as e:
            trans.rollback()
            print("DB 업데이트 중 오류 발생:", e)

        # MySQL 연결 종료
        cursor.close()
        conn.close()

    return recommended_places[["placeName", "latitude", "longitude"]].reset_index(drop=True)

# 사용자의 추천 장소 확인
user_id = 1  # 추천을 받을 사용자 ID
recommendations = recommend_places(user_id)
print(recommendations)


def save_recommendations(user_id, recommendations):
    delete_query = "DELETE FROM Recommendation WHERE userId = %s"
    cursor.execute(delete_query, (user_id,))
    conn.commit()
    
    # 새 추천 데이터 삽입
    insert_query = """
    INSERT INTO Recommendation (userId, placeId, type, season, ageGroup, ranking)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for _, row in recommendations.iterrows():
        cursor.execute(insert_query, (user_id, row["placeId"], row["score"], now))

    conn.commit()

@app.route('/recommend', methods=['GET'])
def get_recommendations():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    recommendations = recommend_places(user_id)
    return jsonify(recommendations)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
