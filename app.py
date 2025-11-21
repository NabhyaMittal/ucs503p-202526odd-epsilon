import os
import json
import ast 
import requests 
import concurrent.futures 
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from urllib.parse import quote_plus 

# --- Gemini Configuration ---
try:
    import google.generativeai as genai
    # NOTE: Using a hardcoded API key is generally unsafe.
    api_key=os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key) 
    model = genai.GenerativeModel('gemini-2.5-flash') 
    print("Gemini model loaded successfully.")
except Exception as e:
    print(f"Error loading Gemini model: {e}")
    model = None

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session_management_4920492'

# --- API Endpoints and Keys ---
WATCHMODE_API_KEY = "rMILd0eTtMFNYr3snedOw34jxBYEEAdMdUEvJb0k" 

# External API URLs
SEARCH_API_URL = "https://id-to-poster-api-3.onrender.com/search_movie"
OVERVIEW_API_URL = "https://imdb-to-overview.onrender.com/get_overview"
RECOMMENDATION_API_URL = "https://recommendor-api-2.onrender.com/recommend"
# The similarity API base URL
SIMILARITY_API_BASE = "https://recommendor-api-2.onrender.com/check_similarity"

SYSTEM_PROMPT = """
You are 'Movie Bot', a cheerful and helpful movie recommendation assistant. 
The user will tell you their mood or preferences. Your job is to:
1.  Understand their mood.
2.  Recommend 3-5 movies that benefits that mood.
3.  Keep your replies conversational, friendly, and concise (like a chatbot).
4.  Do not recommend new movies. movie should be before 2022.
5.  **Crucially, you must ALWAYS respond with a JSON object in the following exact format:**
{
    "reply_to_user": "[Your friendly reply and recommendations go here]", 
    "context": "[A very brief summary of the conversation so far, including the user's last message and your reply. This is for your own memory.]",
    "recommended_movies":["movie1","movie2","movie3"](this should be python list)
}
"""

# --- UTILITY FUNCTIONS ---

def get_streaming_links(imdb_id):
    """Fetches streaming links using the Watchmode API."""
    api_url = f"https://api.watchmode.com/v1/title/{imdb_id}/sources/"
    params = {"apiKey": WATCHMODE_API_KEY}
    
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None

        streaming_links = {}
        for source in data:
            if source.get("type") in ["buy", "rent", "sub"]:
                service_name = source.get("name")
                if service_name and service_name not in streaming_links:
                    streaming_links[service_name] = source.get("web_url")
        
        return streaming_links
        
    except requests.exceptions.RequestException as e:
        print(f"Watchmode API Error for {imdb_id}: {e}")
        return None

def _search_movies_utility(query):
    """Utility function to search the movie catalog."""
    try:
        response = requests.get(SEARCH_API_URL, params={"title": query})
        response.raise_for_status()
        data = response.json()
        
        results = []
        for movie in data:
            results.append({
                "imdb_id": movie.get("imdb_id"), 
                "title": movie.get("title"),
                "poster_path": movie.get("poster_path"),
                "release_year": "N/A", 
                "overview": "Overview temporarily unavailable. Click 'View Details' for more information.",
                "cast": movie.get("cast", "Actor 1, Actor 2") 
            })
        return results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching catalog search results in utility: {e}")
        return []

def _get_movie_details_utility(imdb_id):
    """Utility function to fetch detailed info (overview, rank, full cast)."""
    if not imdb_id or not imdb_id.startswith("tt"):
        return None

    movie_data = {}
    
    try:
        overview_response = requests.get(OVERVIEW_API_URL, params={"imdb_id": imdb_id}, timeout=10)
        overview_response.raise_for_status()
        data = overview_response.json()
        
        if "overview" in data:
            data["description"] = data.pop("overview")

        if "cast" in data and isinstance(data["cast"], str):
            casts_string = data.pop("cast")
            cleaned_string = casts_string.replace('\xa0', ' ').replace('\u00a0', ' ')
            cast_list = [c.strip() for c in cleaned_string.split(',') if c.strip()]
            data["cast"] = cast_list 
            
        movie_data.update(data)
        
        movie_data["poster_url"] = movie_data.pop("full_poster_path", "https://placehold.co/350x500/2f3542/dfe4ea?text=Poster+Unavailable")
        
        if not movie_data.get("rank"):
            movie_data["rank"] = "Rank data unavailable."
        if not movie_data.get("description"):
             movie_data["description"] = "No detailed description found for this movie. The Overview API may be down."
        if not movie_data.get("cast"):
             movie_data["cast"] = ["Detailed Cast Unavailable"]

        return movie_data

    except requests.exceptions.Timeout:
        print(f"Error: Overview API request timed out for {imdb_id}.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie overview for {imdb_id}: {e}")
        return None


def _search_and_extract_movie(movie_name):
    """Searches for a single movie name and returns the required details for the recommendation card."""
    try:
        response = requests.get(SEARCH_API_URL, params={"title": quote_plus(movie_name), "limit": 1})
        response.raise_for_status()
        data = response.json()
        
        if data and data[0].get("imdb_id"):
            return {
                "imdb_id": data[0].get("imdb_id"), 
                "title": data[0].get("title"),
                "poster_path": data[0].get("poster_path"),
            }
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching search results for visual recommendation '{movie_name}': {e}")
        return None

def _fetch_visual_recommendations(movie_names):
    """Fetches visual data for a list of movie names in parallel."""
    if not movie_names or not isinstance(movie_names, list):
        return []
    
    visual_recommendations = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_search_and_extract_movie, name) for name in movie_names]
        
        for future in concurrent.futures.as_completed(futures):
            movie_data = future.result()
            if movie_data:
                visual_recommendations.append(movie_data)
                
    return visual_recommendations


# --- BASE ROUTES ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/catalog")
def catalog():
    return render_template("catalog.html")

@app.route("/recommend")
def recommend():
    return render_template("recommend.html", visual_recommendations=[])

@app.route("/similarity")
def similarity():
    return render_template("similarity.html")

@app.route("/sentiment")
def sentiment():
    return render_template("sentiment.html")


# --- CATALOG ROUTES ---

@app.route('/catalog/results', methods=['GET'])
def catalog_search_results():
    query = request.args.get('q')
    if not query:
        return redirect(url_for('catalog'))
    
    movies = _search_movies_utility(query) 
    session['search_results'] = {movie['imdb_id']: movie for movie in movies}
    
    return render_template('search_results.html', query=query, movies=movies)

@app.route('/catalog/details/<movie_id>', methods=['GET'])
def movie_details(movie_id):
    # Check session for basic info
    basic_movie_data = session.get('search_results', {}).get(movie_id, {})
    
    detailed_data = _get_movie_details_utility(movie_id) 
    cast_list=basic_movie_data.get('cast').replace('  ','').split(',')
    if not detailed_data:
        detailed_data = {"rank": "Rank data unavailable (API failure).","description": "The detailed overview could not be fetched. The external API may be unreachable or returned an error.","cast": cast_list}

    # Determine cast list
    
    movie = {
        "imdb_id": movie_id,
        "title": basic_movie_data.get("title") or detailed_data.get("title", "Unknown Title"),
        "poster_url": basic_movie_data.get("poster_path") or detailed_data.get("poster_url", "https://placehold.co/350x500/2f3542/dfe4ea?text=Poster+Unavailable"),
        "rank": detailed_data.get("rank", "Rank data unavailable."),
        "description": detailed_data.get("description", "No detailed description found for this movie."),
        "cast_members": basic_movie_data.get("cast", ["Cast Unavailable"]).replace('  ','').split(',') 
    }
    
    return render_template('movie_details.html', movie=movie)

# --- API ROUTES ---

@app.route("/search_catalog")
def search_catalog():
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int) 
    
    if not query:
        return jsonify([])

    try:
        response = requests.get(SEARCH_API_URL, params={"title": query})
        response.raise_for_status()
        data = response.json()

        results = []
        for movie in data[:limit]:
            results.append({
                "imdb_id": movie.get("imdb_id"), 
                "title": movie.get("title"),
                "poster_path": movie.get("poster_path") 
            })
        return jsonify(results)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching catalog search results: {e}")
        return jsonify({"error": "External search API failed."}), 500


@app.route("/get_streaming_links")
def api_get_streaming_links():
    imdb_id = request.args.get("imdb_id")
    
    if not imdb_id:
        return jsonify({"error": "No IMDb ID provided"}), 400
        
    links = get_streaming_links(imdb_id)
        
    if links:
        return jsonify(links)
    else:
        return jsonify({"error": "No streaming links found."}), 404


# --- RECOMMENDATION LOGIC ---

@app.route("/get_recommendations", methods=["POST"])
def get_recommendations():
    movie_id = request.form.get("movie_id", "").strip()
    movie_title = request.form.get("movie_title", "Selected Movie").strip()

    if not movie_id:
        return render_template("recommendations_result.html",
                              movie_name=movie_title,
                              recommendations=[],
                              error="Please select a movie from the search results first.")
    
    try:
        url = RECOMMENDATION_API_URL
        response = requests.get(url, params={"imdb_id": movie_id}, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        recommendations = data.get("recommendations", [])
        
        formatted_recs = []
        for rec in recommendations:
            poster = rec.get("poster_path", "")
            if poster and poster.startswith("/"):
                rec["poster_path"] = f"https://image.tmdb.org/t/p/w500{poster}"
            formatted_recs.append(rec)

        # Pass Data Directly to Template (No Session Storage as requested)
        return render_template("recommendations_result.html",
                              movie_name=movie_title,
                              recommendations=formatted_recs,
                              error=None)
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching recommendations: {e}")
        return render_template("recommendations_result.html",
                              movie_name=movie_title,
                              recommendations=[],
                              error="Could not fetch recommendations from the external API.")


# --- SIMILARITY CHECKER (UPDATED PROXY) ---

@app.route("/calculate_similarity", methods=["POST"])
def calculate_similarity():
    """
    Acts as a proxy to the external similarity API to avoid CORS issues.
    Receives ID1 and ID2 from frontend, calls external API, and returns result.
    """
    data = request.json
    id1 = data.get("imdb_id_1")
    id2 = data.get("imdb_id_2")
    title1 = data.get("title1", "Movie 1")
    title2 = data.get("title2", "Movie 2")

    if not id1 or not id2:
        return jsonify({"error": "Please select two movies."}), 400

    try:
        # Call the external API server-side
        # Note: Passing parameters in URL as the external API expects a GET request style
        url = f"{SIMILARITY_API_BASE}?id1={id1}&id2={id2}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        api_data = response.json()
        
        # Return the whole response from external API + titles for the frontend
        return jsonify({
            "score_percent": api_data.get("cosine_similarity"), # Raw score, converted in JS
            "cosine_similarity": api_data.get("cosine_similarity"),
            "movie1_title": title1,
            "movie2_title": title2
        })
        
    except requests.exceptions.RequestException as e:
        print(f"Error in /calculate_similarity proxy: {e}")
        return jsonify({"error": "Could not calculate similarity via external API."}), 500


# --- CHATBOT ROUTE ---

@app.route("/chat", methods=["POST"])
def chat():
    if not model:
        return jsonify({"error": "AI model is not configured."}), 500

    try:
        data = request.json
        user_message = data.get("message")
        context = data.get("context", "")

        if not context:
            prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}"
        else:
            prompt = f"{SYSTEM_PROMPT}\n\nPrevious Context: {context}\n\nUser: {user_message}"

        # --- DIAGNOSTIC STEP 1: Check LLM Response ---
        print(f"--- Calling LLM with prompt for user: {user_message[:50]}...")
        
        response = model.generate_content(prompt)
        
        response_text = response.text.strip()
        print(f"--- RAW LLM Response Text: {response_text[:500]}...") # Print the raw output
        
        start_index = response_text.find('{')
        end_index = response_text.rfind('}')
        
        if start_index == -1 or end_index == -1:
            # This is correct handling for malformed JSON structure
            raise json.JSONDecodeError("JSON delimiters not found or malformed.", response_text, 0)
            
        json_string = response_text[start_index:end_index+1].strip()
        response_data = json.loads(json_string)
        
        recommended_movies = response_data.get("recommended_movies", [])

        # --- DIAGNOSTIC STEP 2: Check _fetch_visual_recommendations ---
        print(f"--- Recommended Movies found: {recommended_movies}")
        
        visual_recommendations = _fetch_visual_recommendations(recommended_movies) # Likely crash point
        
        response_data['visual_recommendations'] = visual_recommendations
        
        return jsonify(response_data)

    except json.JSONDecodeError as e:
        # This handles cases where the model returns invalid JSON syntax
        print(f"JSONDecodeError: {e} | Raw Text causing error: {response_text[:100]}")
        return jsonify({"reply_to_user": "Sorry, I got a little confused. Could you rephrase that?"}), 200
        
    except Exception as e:
        # This catch-all now prints the actual error for diagnosis
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"CRITICAL UNCAUGHT CHAT ERROR: {type(e).__name__}: {e}")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return jsonify({"error": "Sorry, I'm having trouble thinking right now."}), 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))