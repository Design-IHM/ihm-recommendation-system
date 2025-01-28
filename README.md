# Système de Recommandation de Bibliothèque Numérique

Ce projet implémente un système de recommandation pour une bibliothèque numérique utilisant Firebase Functions et le filtrage collaboratif.

## Configuration requise

- Node.js (version 18 ou supérieure)
- Firebase CLI
- Compte Firebase

## Installation

1. Installez les dépendances :
```bash
npm install
```

2. Configurez Firebase :
```bash
firebase login
firebase init
```

3. Déployez les fonctions :
```bash
firebase deploy --only functions
```

## Endpoints API

### 1. Obtenir des recommandations personnalisées
```
GET /recommendations/user/:userId
```

### 2. Obtenir les livres populaires
```
GET /recommendations/popular
```

### 3. Mettre à jour l'historique de lecture
```
POST /user/:userId/history
Body: {
    "bookId": "string",
    "rating": number
}
```

## Structure de la base de données Firestore

### Collection 'users'
```javascript
{
    userId: {
        readingHistory: {
            bookId: rating // rating de 1 à 5
        }
    }
}
```

### Collection 'books'
```javascript
{
    bookId: {
        title: string,
        author: string,
        genre: string,
        borrowCount: number
    }
}
```

## Algorithme de recommandation

Le système utilise un algorithme de filtrage collaboratif basé sur la similarité entre utilisateurs :

1. Calcul de la similarité entre utilisateurs (similarité cosinus)
2. Identification des utilisateurs similaires
3. Recommandation des livres appréciés par les utilisateurs similaires

## Tests

Pour exécuter les tests :
```bash
npm test
```
