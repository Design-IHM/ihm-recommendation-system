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
    """
    Page d'accueil avec les endpoints disponibles
    ---
    responses:
      200:
        description: Accueil de l'API avec une liste des endpoints disponibles
        schema:
          type: object
          properties:
            message:
              type: string
            endpoints:
              type: object
              additionalProperties:
                type: string
    """
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
    """
    Rechercher des livres similaires en fonction du contenu et du titre.
    ---
    parameters:
      - in: body
        name: book
        description: Objet contenant le titre du livre
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
              example: "Titre du livre"
    responses:
      200:
        description: Liste des livres similaires
        schema:
          type: object
          properties:
            base_book:
              type: object
              description: Le livre de base utilisé pour la comparaison
            similar_books:
              type: array
              items:
                type: object
              description: Liste des livres similaires
      400:
        description: Erreur de validation (par exemple, titre manquant)
      404:
        description: Livre non trouvé
      500:
        description: Erreur interne du serveur
    """
    try:
        data = request.get_json()
        book_title = data.get('title', '').strip()

        if not book_title:
            return jsonify({"error": "Le titre du livre est requis."}), 400

        # Récupérer tous les livres
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
        return jsonify({"error": f"Erreur interne: {str(e)}"}), 500


@app.route('/recommendations/similar-users/<user_email>')
def get_similar_users_recommendations(user_email):
    """
    Recommandations basées sur les utilisateurs similaires.
    ---
    parameters:
      - in: path
        name: user_email
        type: string
        required: true
        description: L'email de l'utilisateur pour lequel obtenir les recommandations.
    responses:
      200:
        description: Liste des recommandations basées sur les utilisateurs similaires
        schema:
          type: object
          properties:
            recommendations:
              type: array
              items:
                type: object
                description: Liste des documents recommandés
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur interne du serveur
    """
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
        return jsonify({'error': f"Erreur interne: {str(e)}"}), 500

@app.route('/recommendations/popular')
def get_popular_books():
    """
    Obtient les livres les plus populaires basés sur les consultations récentes.
    ---
    responses:
      200:
        description: Liste des livres populaires recommandés
        schema:
          type: object
          properties:
            popular_books:
              type: array
              items:
                type: object
                description: Liste des livres populaires avec leur score de popularité
      500:
        description: Erreur interne du serveur
    """
    try:
        # Obtenir tous les utilisateurs
        users_ref = db.collection('BiblioUser')
        users = users_ref.stream()

        # Compter les occurrences de chaque livre
        book_counts = Counter()

        for user in users:
            user_data = user.to_dict()
            if 'docRecent' in user_data:
                for doc in user_data['docRecent']:
                    if 'nameDoc' in doc:
                        book_counts[doc['nameDoc']] += 1

        # Obtenir les détails des livres les plus populaires
        popular_books = []
        books_ref = db.collection('BiblioInformatique')

        for book_name, count in book_counts.most_common(10):
            # Chercher le livre dans la collection
            query = books_ref.where('name', '==', book_name).limit(1)
            book_docs = query.stream()

            for book in book_docs:
                book_data = book.to_dict()
                book_data['id'] = book.id
                book_data['popularity_score'] = count
                popular_books.append(book_data)

        return jsonify({'popular_books': popular_books})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/user/<user_id>/history', methods=['POST'])
def update_reading_history(user_id):
    """
    Met à jour l'historique de lecture d'un utilisateur avec un livre et une note.
    ---
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
        description: L'ID de l'utilisateur
      - in: body
        name: history
        description: Données de mise à jour de l'historique
        required: true
        schema:
          type: object
          properties:
            bookId:
              type: string
              description: L'ID du livre
              example: "12345"
            rating:
              type: number
              format: float
              description: La note attribuée au livre (sur 5)
              example: 4.5
    responses:
      200:
        description: Historique mis à jour avec succès
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Historique mis à jour avec succès"
      400:
        description: Données invalides (par exemple, note incorrecte)
      500:
        description: Erreur interne du serveur
    """
    try:
        data = request.get_json()
        book_id = data.get('bookId')
        rating = data.get('rating')

        if not book_id or not isinstance(rating, (int, float)) or rating < 0 or rating > 5:
            return jsonify({"error": "Données invalides"}), 400

        user_ref = db.collection('BiblioUser').document(user_id)
        user_ref.set({
            'readingHistory': {
                book_id: rating
            }
        }, merge=True)

        return jsonify({"message": "Historique mis à jour avec succès"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/user/<user_id>/preferences')
def get_user_preferences(user_id):
    """
    Obtient les préférences de l'utilisateur basées sur son historique de lecture.
    ---
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
        description: L'ID de l'utilisateur
    responses:
      200:
        description: Préférences de lecture de l'utilisateur
        schema:
          type: object
          properties:
            categories:
              type: object
              additionalProperties:
                type: integer
            types:
              type: object
              additionalProperties:
                type: integer
      404:
        description: Utilisateur non trouvé
      500:
        description: Erreur interne du serveur
    """
    try:
        user_ref = db.collection('BiblioUser').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        user_data = user_doc.to_dict()
        preferences = {
            'categories': Counter(),
            'types': Counter()
        }

        if 'docRecentRegarder' in user_data:
            for doc in user_data['docRecentRegarder']:
                if 'cathegorieDoc' in doc:
                    preferences['categories'][doc['cathegorieDoc']] += 1
                if 'type' in doc:
                    preferences['types'][doc['type']] += 1

        return jsonify(preferences)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recommendations/user/<user_id>')
def get_user_recommendations(user_id):
    """
    Obtient des recommandations de livres personnalisées pour un utilisateur basé sur ses préférences.
    ---
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
        description: L'ID de l'utilisateur
    responses:
      200:
        description: Liste des recommandations de livres
        schema:
          type: object
          properties:
            recommendations:
              type: array
              items:
                type: object
                description: Liste des livres recommandés avec un score de pertinence
      500:
        description: Erreur interne du serveur
    """
    try:
        # Obtenir les préférences de l'utilisateur
        user_preferences = get_user_preferences(user_id)

        if not user_preferences:
            return jsonify({"error": "Aucune préférence trouvée pour cet utilisateur"}), 404

        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        recommendations = []
        for book in books:
            score = calculate_book_score(book, user_preferences)
            if score > 0:
                book_data = book.to_dict()
                book_data['score'] = score
                recommendations.append(book_data)

        recommendations = sorted(recommendations, key=lambda x: x['score'], reverse=True)

        return jsonify({'recommendations': recommendations})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    app.run(debug=False)
