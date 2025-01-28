from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os
from collections import Counter
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Initialisation de Flask
app = Flask(__name__)
CORS(app)

# Chemin vers le fichier service-account-key.json
current_dir = os.path.dirname(os.path.abspath(__file__))
cred = credentials.Certificate(os.path.join(current_dir, 'service-account-key.json'))

# Initialisation de Firebase Admin
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

@app.route('/similarbooks', methods=['POST'])
def similar_books():
    try:
        data = request.get_json()
        book_title = data.get('title', '').strip()

        if not book_title:
            return jsonify({"error": "Le titre du livre est requis."}), 400

        # Fetch all books from Firebase
        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        # Construct the books_list, eliminating books without the 'name' attribute
        books_list = [
            {"id": book.id, **book.to_dict()}
            for book in books
            if 'name' in book.to_dict()  # Only include books with the 'name' field
        ]

        if not books_list:
            return jsonify({"error": "Aucun livre avec un champ 'name' trouvé dans la base de données."}), 404

        # Find the book with the given title
        base_book = next((book for book in books_list if book['name'].lower() == book_title.lower()), None)
        if not base_book:
            return jsonify({"error": "Livre non trouvé dans la base de données."}), 404

        # Extract titles and descriptions
        titles = [book['name'] for book in books_list]
        descriptions = [book.get('desc', '') for book in books_list]

        # TF-IDF Vectorization
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(descriptions)

        # Compute cosine similarity
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # Find the index of the base book
        base_index = titles.index(base_book['name'])
        similarity_scores = list(enumerate(similarity_matrix[base_index]))
        similarity_scores = sorted(similarity_scores, key=lambda x: x[1], reverse=True)

        # Retrieve top 5 similar books (excluding the base book)
        similar_books_indices = [i for i, score in similarity_scores if i != base_index][:5]
        similar_books = [books_list[i] for i in similar_books_indices]

        return jsonify({
            "base_book": base_book,
            "similar_books": similar_books
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def calculate_user_similarity(user1_data, user2_data):
    """
    Calcule la similarité entre deux utilisateurs basée sur 4 critères :
    1. Même département (40%)
    2. Même niveau d'études (20%)
    3. Historique de consultation récent similaire (25%)
    4. Types de documents consultés similaires (15%)
    """
    try:
        similarity_score = 0.0

        # 1. Même département (40 points)
        dept1 = user1_data.get('departement', '')
        dept2 = user2_data.get('departement', '')
        if dept1 and dept2 and dept1 == dept2:
            similarity_score += 40.0

        # 2. Même niveau d'études (20 points)
        # Convertir "level5" en "5" pour la comparaison
        level1 = user1_data.get('level', '').replace('level', '') if user1_data.get('level') else ''
        level2 = user2_data.get('level', '').replace('level', '') if user2_data.get('level') else ''
        if level1 and level2 and level1 == level2:
            similarity_score += 20.0

        # 3. Historique de consultation récent (25 points)
        recent_docs1 = user1_data.get('docRecentRegarder', [])
        recent_docs2 = user2_data.get('docRecentRegarder', [])

        # Créer des ensembles de paires (catégorie, type)
        docs1_set = {(str(doc.get('cathegorieDoc', '')), str(doc.get('type', '')))
                    for doc in recent_docs1 if isinstance(doc, dict)}
        docs2_set = {(str(doc.get('cathegorieDoc', '')), str(doc.get('type', '')))
                    for doc in recent_docs2 if isinstance(doc, dict)}

        # Calculer l'intersection
        if docs1_set and docs2_set:
            common_docs = docs1_set.intersection(docs2_set)
            overlap_ratio = float(len(common_docs)) / float(max(len(docs1_set), len(docs2_set)))
            similarity_score += 25.0 * overlap_ratio

        # 4. Types de documents similaires (15 points)
        types1 = Counter(str(doc.get('type', '')) for doc in recent_docs1 if isinstance(doc, dict))
        types2 = Counter(str(doc.get('type', '')) for doc in recent_docs2 if isinstance(doc, dict))

        # Calculer la similarité des types
        all_types = set(types1.keys()) | set(types2.keys())
        if all_types:
            type_similarity = sum(min(types1[t], types2[t]) for t in all_types) / float(max(1, sum(max(types1[t], types2[t]) for t in all_types)))
            similarity_score += 15.0 * type_similarity

        return float(similarity_score)
    except Exception as e:
        print(f"Erreur dans calculate_user_similarity: {str(e)}")
        return 0.0

@app.route('/recommendations/similar-users/<user_email>')
def get_similar_users_recommendations(user_email):
    """Obtient des recommandations basées sur les utilisateurs similaires"""
    try:
        # Obtenir l'utilisateur cible
        user_ref = db.collection('BiblioUser').document(user_email)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404

        user_data = user_doc.to_dict()

        # Obtenir tous les utilisateurs
        users_ref = db.collection('BiblioUser')
        all_users = users_ref.stream()

        # Calculer la similarité avec chaque utilisateur
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

        # Trier par similarité
        similar_users.sort(key=lambda x: x['similarity'], reverse=True)

        # Obtenir les recommandations des utilisateurs similaires
        recommendations = []
        seen_docs = {str(doc.get('nameDoc', '')) for doc in user_data.get('docRecent', []) if isinstance(doc, dict)}

        # Prendre les 5 utilisateurs les plus similaires
        for similar_user in similar_users[:5]:
            # Pondérer les recommandations par la similarité
            weight = float(similar_user['similarity']) / 100.0
            for doc in similar_user['recent_docs']:
                if not isinstance(doc, dict):
                    continue

                doc_name = str(doc.get('nameDoc', ''))
                if doc_name and doc_name not in seen_docs:
                    doc_copy = doc.copy()  # Créer une copie pour ne pas modifier l'original
                    doc_copy['recommendation_score'] = weight * 100.0
                    doc_copy['recommended_by'] = similar_user['user_id']
                    doc_copy['similarity_score'] = similar_user['similarity']
                    recommendations.append(doc_copy)
                    seen_docs.add(doc_name)

        # Trier les recommandations par score et prendre les 10 meilleures
        recommendations.sort(key=lambda x: x.get('recommendation_score', 0), reverse=True)
        top_recommendations = recommendations[:10]

        return jsonify({
            'recommendations': top_recommendations,
            'similar_users': [{
                'user_id': u['user_id'],
                'similarity': u['similarity']
            } for u in similar_users[:5]],
            'user_info': {
                'departement': user_data.get('departement', ''),
                'level': user_data.get('level', '')
            }
        })

    except Exception as e:
        print(f"Erreur dans get_similar_users_recommendations: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    """Page d'accueil avec la liste des endpoints disponibles"""
    return jsonify({
        "message": "Bienvenue sur l'API de recommandation de livres",
        "endpoints": {
            "test": "/test",
            "recommandations_utilisateur": "/recommendations/user/<user_id>",
            "livres_populaires": "/recommendations/popular",
            "mise_a_jour_historique": "/user/<user_id>/history (POST)",
            "recommandations_similaires": "/recommendations/similar-users/<user_email>"
        }
    })

@app.route('/test')
def test():
    """Route de test simple"""
    return jsonify({"message": "API fonctionne!"})

@app.route('/recommendations/user/<user_id>')
def get_user_recommendations(user_id):
    """Obtient des recommandations personnalisées pour un utilisateur"""
    try:
        # Obtenir les préférences de l'utilisateur
        user_preferences = get_user_preferences(user_id)
        if not user_preferences:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404

        # Obtenir les utilisateurs similaires
        similar_users = get_similar_users(user_id)

        # Obtenir tous les livres
        books_ref = db.collection('BiblioInformatique')
        books = books_ref.stream()

        # Calculer les scores pour chaque livre
        scored_books = []
        for book in books:
            base_score = calculate_book_score(book, user_preferences)

            # Bonus basé sur les préférences des utilisateurs similaires
            similarity_bonus = 0
            for similar_user in similar_users[:5]:  # Utiliser les 5 utilisateurs les plus similaires
                sim_score = calculate_book_score(book, similar_user['preferences'])
                similarity_bonus += (sim_score * similar_user['similarity']) / 10

            final_score = base_score + similarity_bonus

            book_data = book.to_dict()
            book_data['id'] = book.id
            book_data['score'] = final_score
            book_data['base_score'] = base_score
            book_data['similarity_bonus'] = similarity_bonus

            scored_books.append(book_data)

        # Trier les livres par score et prendre les 10 meilleurs
        recommendations = sorted(scored_books, key=lambda x: x['score'], reverse=True)[:10]

        return jsonify({
            'recommendations': recommendations,
            'user_preferences': {
                'top_categories': dict(user_preferences['categories'].most_common(3)),
                'top_types': dict(user_preferences['types'].most_common(3))
            },
            'similar_users_count': len(similar_users)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/recommendations/popular')
def get_popular_books():
    """Obtient les livres les plus populaires basés sur les consultations récentes"""
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
    """Mettre à jour l'historique de lecture d'un utilisateur"""
    try:
        data = request.get_json()
        book_id = data.get('bookId')
        rating = data.get('rating')

        if not book_id or not isinstance(rating, (int, float)) or rating < 0 or rating > 5:
            return jsonify({"error": "Données invalides"}), 400

        user_ref = db.collection('users').document(user_id)
        user_ref.set({
            'readingHistory': {
                book_id: rating
            }
        }, merge=True)

        return jsonify({"message": "Historique mis à jour avec succès"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_user_preferences(user_id):
    """Obtient les préférences de l'utilisateur basées sur son historique"""
    user_ref = db.collection('BiblioUser').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        return None

    user_data = user_doc.to_dict()
    preferences = {
        'categories': Counter(),
        'types': Counter()
    }

    # Analyse des documents récemment regardés
    if 'docRecentRegarder' in user_data:
        for doc in user_data['docRecentRegarder']:
            if 'cathegorieDoc' in doc:
                preferences['categories'][doc['cathegorieDoc']] += 1
            if 'type' in doc:
                preferences['types'][doc['type']] += 1

    return preferences

def calculate_book_score(book, user_preferences):
    """Calcule un score de pertinence pour un livre basé sur les préférences de l'utilisateur"""
    if not user_preferences:
        return 0

    score = 0
    book_data = book.to_dict()

    # Score basé sur la catégorie (30% du score final)
    if 'cathegorie' in book_data:
        score += (user_preferences['categories'][book_data['cathegorie']] * 3)

    # Score basé sur le type (20% du score final)
    if 'type' in book_data:
        score += (user_preferences['types'][book_data['type']] * 2)

    # Score basé sur les notes des utilisateurs (40% du score final)
    if 'commentaire' in book_data and isinstance(book_data['commentaire'], list):
        notes = [c.get('note', 0) for c in book_data['commentaire'] if isinstance(c, dict)]
        if notes:
            avg_note = sum(notes) / len(notes)
            score += (avg_note * 4)  # Les notes sont sur 5, donc max 4 points

    # Bonus pour les livres disponibles (10% du score final)
    if 'exemplaire' in book_data and book_data['exemplaire'] > 0:
        score += 1

    return score

def get_similar_users(user_id):
    """Trouve des utilisateurs similaires basés sur leurs préférences de lecture"""
    users_ref = db.collection('BiblioUser')
    users = users_ref.stream()

    # Obtenir les préférences de l'utilisateur cible
    target_preferences = get_user_preferences(user_id)
    if not target_preferences:
        return []

    similar_users = []
    for user in users:
        if user.id != user_id:
            user_prefs = get_user_preferences(user.id)
            if user_prefs:
                similarity = 0
                # Comparer les catégories préférées
                for category in target_preferences['categories']:
                    similarity += min(target_preferences['categories'][category],
                                   user_prefs['categories'].get(category, 0))
                # Comparer les types préférés
                for type_ in target_preferences['types']:
                    similarity += min(target_preferences['types'][type_],
                                   user_prefs['types'].get(type_, 0))

                if similarity > 0:
                    similar_users.append({
                        'user_id': user.id,
                        'similarity': similarity,
                        'preferences': user_prefs
                    })

    return sorted(similar_users, key=lambda x: x['similarity'], reverse=True)

if __name__ == '__main__':
    app.run(debug=False)
