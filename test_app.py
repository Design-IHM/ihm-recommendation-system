import pytest
from app import app, calculate_user_similarity

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_route_test(client):
    """Test de la route /test"""
    response = client.get('/test')
    assert response.status_code == 200
    assert response.json == {"message": "API fonctionne!"}

def test_calculate_user_similarity():
    """Test de la fonction de calcul de similarité"""
    user1_history = {
        'book1': 5,
        'book2': 4
    }
    user2_history = {
        'book1': 4,
        'book2': 3
    }
    
    similarity = calculate_user_similarity(user1_history, user2_history)
    assert isinstance(similarity, (int, float))
    assert 0 <= similarity <= 5

def test_get_recommendations(client):
    """Test de la route des recommandations"""
    response = client.get('/recommendations/user/user1')
    assert response.status_code in [200, 404]  # 404 si l'utilisateur n'existe pas

def test_get_popular_books(client):
    """Test de la route des livres populaires"""
    response = client.get('/recommendations/popular')
    assert response.status_code == 200
    assert 'books' in response.json

def test_update_history(client):
    """Test de la mise à jour de l'historique"""
    data = {
        'bookId': 'book1',
        'rating': 5
    }
    response = client.post('/user/user1/history', json=data)
    assert response.status_code in [200, 400]  # 400 si les données sont invalides
