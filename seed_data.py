import firebase_admin
from firebase_admin import credentials, firestore
import os

# Configuration de l'émulateur Firestore
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"

# Chemin vers le fichier service-account-key.json
current_dir = os.path.dirname(os.path.abspath(__file__))
cred = credentials.Certificate(os.path.join(current_dir, 'user-based', 'service-account-key.json'))

# Initialisation de Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'projectId': 'syst-recommandation'
    })

db = firestore.client()

# Données de test pour les livres
books = [
    {
        "title": "Le Petit Prince",
        "author": "Antoine de Saint-Exupéry",
        "genre": ["Fiction", "Jeunesse"],
        "description": "Un conte philosophique sur l'amitié",
        "publishedYear": 1943,
        "language": "Français",
        "coverImage": "https://example.com/petit-prince.jpg",
        "borrowCount": 150
    },
    {
        "title": "1984",
        "author": "George Orwell",
        "genre": ["Science-Fiction", "Dystopie"],
        "description": "Un roman sur la surveillance de masse",
        "publishedYear": 1949,
        "language": "Anglais",
        "coverImage": "https://example.com/1984.jpg",
        "borrowCount": 200
    },
    {
        "title": "Notre-Dame de Paris",
        "author": "Victor Hugo",
        "genre": ["Classique", "Historique"],
        "description": "Une histoire d'amour dans le Paris médiéval",
        "publishedYear": 1831,
        "language": "Français",
        "coverImage": "https://example.com/notre-dame.jpg",
        "borrowCount": 120
    }
]

# Données de test pour les utilisateurs
users = {
    "user1": {
        "name": "Alice",
        "readingHistory": {
            "book1": 5,  # Aime Le Petit Prince
            "book2": 4   # Aime bien 1984
        }
    },
    "user2": {
        "name": "Bob",
        "readingHistory": {
            "book2": 5,  # Aime 1984
            "book3": 4   # Aime bien Notre-Dame
        }
    },
    "user3": {
        "name": "Charlie",
        "readingHistory": {
            "book1": 5,  # Aime Le Petit Prince
            "book3": 5   # Aime Notre-Dame
        }
    }
}

def seed_database():
    """Peuple la base de données avec les données de test"""
    try:
        # Ajout des livres
        for i, book in enumerate(books, 1):
            db.collection('books').document(f'book{i}').set(book)
            print(f"Livre ajouté: {book['title']}")

        # Ajout des utilisateurs
        for user_id, user_data in users.items():
            db.collection('users').document(user_id).set(user_data)
            print(f"Utilisateur ajouté: {user_data['name']}")

        print("Base de données peuplée avec succès!")

    except Exception as e:
        print(f"Erreur lors du peuplement de la base de données: {e}")

if __name__ == "__main__":
    seed_database()
