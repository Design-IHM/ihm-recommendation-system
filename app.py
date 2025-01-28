from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Initialisation de Firebase Admin
current_dir = os.path.dirname(os.path.abspath(__file__))
cred = credentials.Certificate(os.path.join(current_dir, 'service-account-key.json'))

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'projectId': 'test-b1637'
    })

db = firestore.client()

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def home():
    """Page d'accueil avec les endpoints disponibles"""
    return jsonify({
        "message": "Bienvenue sur l'API de recommandation de livres",
        "endpoints": {
            "Test API": "/test",
            "Similaires à un livre": "/similarbooks (POST)",
            "Recommandations basées sur utilisateurs similaires": "/recommendations/similar-users/<user_email>",
            "Livres populaires": "/recommendations/popular",
            "Recommandations personnalisées pour un utilisateur": "/recommendations/user/<user_id>",
            "Mettre à jour l'historique utilisateur": "/user/<user_id>/history (POST)"
        }
    })

@app.route('/test')
def test():
    """Route de test simple"""
    return jsonify({"message": "API fonctionne !"})

@app.route('/similarbooks', methods=['POST'])
def similar_books():
    """Rechercher des livres similaires en fonction du contenu et du titre"""
    try:
        data = request.get_json()
        book_title = data.get('title', '').strip()

        if not book_title:
            return jsonify({"error": "Le titre du livre est requis."}), 400

        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        books_list = [
            {"id": book.id, **book.to_dict()}
            for book in books
            if 'name' in book.to_dict()
        ]

        base_book = next((book for book in books_list if book['name'].lower() == book_title.lower()), None)
        if not base_book:
            return jsonify({"error": "Livre non trouvé."}), 404

        descriptions = [book.get('desc', '') for book in books_list]
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(descriptions)

        similarity_matrix = cosine_similarity(tfidf_matrix)
        base_index = [book['name'] for book in books_list].index(base_book['name'])
        similarity_scores = sorted(
            enumerate(similarity_matrix[base_index]),
            key=lambda x: x[1],
            reverse=True
        )

        similar_books = [
            books_list[i] for i, score in similarity_scores if i != base_index
        ][:5]

        return jsonify({
            "base_book": base_book,
            "similar_books": similar_books
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recommendations/similar-users/<user_email>')
def get_similar_users_recommendations(user_email):
    """Recommandations basées sur les utilisateurs similaires"""
    try:
        users_ref = db.collection('users')
        users = users_ref.stream()

        user_data = [
            {"email": user.id, **user.to_dict()}
            for user in users
        ]

        current_user = next((u for u in user_data if u['email'] == user_email), None)
        if not current_user:
            return jsonify({"error": "Utilisateur non trouvé."}), 404

        def calculate_user_similarity(user1, user2):
            common_books = set(user1['history']).intersection(user2['history'])
            return len(common_books) / len(set(user1['history']).union(user2['history']))

        similarities = [
            {
                "email": u['email'],
                "similarity": calculate_user_similarity(current_user, u)
            }
            for u in user_data if u['email'] != user_email
        ]

        similarities = sorted(similarities, key=lambda x: x['similarity'], reverse=True)
        most_similar_user = similarities[0] if similarities else None

        if not most_similar_user:
            return jsonify({"message": "Aucun utilisateur similaire trouvé."})

        similar_user = next(u for u in user_data if u['email'] == most_similar_user['email'])
        recommended_books = set(similar_user['history']) - set(current_user['history'])

        return jsonify({
            "recommended_books": list(recommended_books)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recommendations/user/<user_id>')
def get_user_recommendations(user_id):
    """Recommandations personnalisées pour un utilisateur"""
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Utilisateur non trouvé."}), 404

        user_data = user_doc.to_dict()
        user_history = set(user_data.get('history', []))

        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        all_books = [book.to_dict() for book in books]
        recommended_books = [
            book for book in all_books if book['name'] not in user_history
        ]

        return jsonify({"recommended_books": recommended_books})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recommendations/popular')
def get_popular_books():
    """Livres les plus populaires"""
    try:
        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        books_list = [book.to_dict() for book in books]
        popularity_counter = Counter(
            book['name'] for book in books_list if 'name' in book
        )

        most_popular_books = popularity_counter.most_common(5)
        return jsonify({"popular_books": most_popular_books})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/user/<user_id>/history', methods=['POST'])
def update_reading_history(user_id):
    """Mettre à jour l'historique d'un utilisateur"""
    try:
        data = request.get_json()
        book_name = data.get('book_name', '').strip()

        if not book_name:
            return jsonify({"error": "Le nom du livre est requis."}), 400

        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Utilisateur non trouvé."}), 404

        user_data = user_doc.to_dict()
        history = user_data.get('history', [])

        if book_name not in history:
            history.append(book_name)
            user_ref.update({"history": history})

        return jsonify({"message": "Historique mis à jour avec succès."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
