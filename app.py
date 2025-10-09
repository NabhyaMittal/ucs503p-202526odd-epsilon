from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np

app = Flask(__name__)

# Load dataset
df = pd.read_csv(r"D:\SE project\the_final.csv")

# Build mappings
id_to_title = dict(zip(df["id"], df["title"]))
title_to_id = {v.lower(): k for k, v in id_to_title.items()}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/catalog")
def catalog():
    return render_template("catalog.html")


@app.route("/recommend")
def recommend():
    return render_template("recommend.html")


@app.route("/similarity")
def similarity():
    return render_template("similarity.html")


@app.route("/sentiment")
def sentiment():
    return render_template("sentiment.html")


# --- AJAX endpoint for live movie search ---
@app.route("/search_movie")
def search_movie():
    query = request.args.get("q", "").lower()
    results = []
    if query:
        results = [t for t in df["title"] if query in t.lower()]
    return jsonify(results[:10])


# --- Recommendation result page ---
@app.route("/get_recommendations", methods=["POST"])
def get_recommendations():
    movie_title = request.form.get("movie_name", "").strip().lower()

    if movie_title not in title_to_id:
        return render_template("recommendations_result.html",
                               movie_name=movie_title,
                               recommendations=[],
                               error="Movie not found in dataset.")

    movie_id = title_to_id[movie_title]
    row = df[df["id"] == movie_id]

    if "most_similar_20" not in df.columns:
        return render_template("recommendations_result.html",
                               movie_name=movie_title,
                               recommendations=[],
                               error="No recommendation data found.")

    similar_ids_str = row["most_similar_20"].values[0]
    similar_ids = np.array(eval(similar_ids_str.replace(' ', ',')))
    recommendations_id = [int(i[0]) for i in similar_ids]
    recommendations=list(df[df["id"].isin(recommendations_id)]["title"])
    return render_template("recommendations_result.html",
                           movie_name=movie_title.title(),
                           recommendations=recommendations,
                           error=None)


if __name__ == "__main__":
    app.run(debug=True)
