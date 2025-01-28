from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json

# Charger les variables d'environnement
load_dotenv()

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Charger la clé Firebase depuis une variable d'environnement
firebase_key_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if not firebase_key_json:
    raise ValueError("La variable d'environnement GOOGLE_APPLICATION_CREDENTIALS_JSON est manquante.")

firebase_key = json.loads(firebase_key_json)
cred = credentials.Certificate(firebase_key)

# Initialisation de Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'projectId': firebase_key['project_id']
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
            "test": "/test",
            "recommandations_livres_similaires": "/similarbooks (POST)",
            "recommandations_utilisateurs_similaires": "/recommendations/similar-users/<user_email>",
            "livres_populaires": "/recommendations/popular",
            "recommandations_utilisateur": "/recommendations/user/<user_id>",
            "mise_a_jour_historique": "/user/<user_id>/history (POST)"
        }
    })

@app.route('/test')
def test():
    """Route de test simple"""
    return jsonify({"message": "API fonctionne correctement !"})

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
        user_ref = db.collection('BiblioUser').document(user_email)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404

        user_data = user_doc.to_dict()

        users_ref = db.collection('BiblioUser')
        all_users = users_ref.stream()

        similar_users = []
        for other_user in all_users:
            if other_user.id != user_email:
                other_user_data = other_user.to_dict()
                if not isinstance(other_user_data, dict):
                    continue

                similarity = calculate_user_similarity(user_data, other_user_data)

                if similarity > 30.0:  # Seuil minimum de similarité (30%)
                    similar_users.append({
                        'user_id': other_user.id,
                        'similarity': similarity,
                        'recent_docs': other_user_data.get('docRecent', [])
                    })

        similar_users.sort(key=lambda x: x['similarity'], reverse=True)

        recommendations = []
        seen_docs = {str(doc.get('nameDoc', '')) for doc in user_data.get('docRecent', []) if isinstance(doc, dict)}

        for similar_user in similar_users[:5]:
            weight = float(similar_user['similarity']) / 100.0
            for doc in similar_user['recent_docs']:
                if not isinstance(doc, dict):
                    continue

                doc_name = str(doc.get('nameDoc', ''))
                if doc_name and doc_name not in seen_docs:
                    doc_copy = doc.copy()
                    doc_copy['recommendation_score'] = weight * 100.0
                    doc_copy['recommended_by'] = similar_user['user_id']
                    recommendations.append(doc_copy)
                    seen_docs.add(doc_name)

        recommendations.sort(key=lambda x: x.get('recommendation_score', 0), reverse=True)
        return jsonify({
            'recommendations': recommendations
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Ajoutez d'autres routes si besoin...

if __name__ == '__main__':
    app.run(debug=False)
