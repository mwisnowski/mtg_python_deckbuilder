"""Tests for web tag search endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the web app."""
    # Import here to avoid circular imports
    from code.web.app import app
    return TestClient(app)


def test_theme_autocomplete_basic(client):
    """Test basic theme autocomplete functionality."""
    response = client.get("/commanders/theme-autocomplete?theme=life&limit=5")
    
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    
    content = response.text
    assert "autocomplete-item" in content
    assert "Life" in content  # Should match tags starting with "life"
    assert "tag-count" in content  # Should show card counts


def test_theme_autocomplete_min_length(client):
    """Test that theme autocomplete requires minimum 2 characters."""
    response = client.get("/commanders/theme-autocomplete?theme=a&limit=5")
    
    # Should fail validation
    assert response.status_code == 422


def test_theme_autocomplete_no_matches(client):
    """Test theme autocomplete with query that has no matches."""
    response = client.get("/commanders/theme-autocomplete?theme=zzzzzzzzz&limit=5")
    
    assert response.status_code == 200
    content = response.text
    assert "autocomplete-empty" in content or "No matching themes" in content


def test_theme_autocomplete_limit(client):
    """Test that theme autocomplete respects limit parameter."""
    response = client.get("/commanders/theme-autocomplete?theme=a&limit=3")
    
    assert response.status_code in [200, 422]  # May fail min_length validation
    
    # Try with valid length
    response = client.get("/commanders/theme-autocomplete?theme=to&limit=3")
    assert response.status_code == 200
    
    # Count items (rough check - should have at most 3)
    content = response.text
    item_count = content.count('class="autocomplete-item"')
    assert item_count <= 3


def test_api_cards_by_tags_and_logic(client):
    """Test card search with AND logic."""
    response = client.get("/api/cards/by-tags?tags=tokens&logic=AND&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "tags" in data
    assert "logic" in data
    assert data["logic"] == "AND"
    assert "total_matches" in data
    assert "cards" in data
    assert isinstance(data["cards"], list)


def test_api_cards_by_tags_or_logic(client):
    """Test card search with OR logic."""
    response = client.get("/api/cards/by-tags?tags=tokens,sacrifice&logic=OR&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["logic"] == "OR"
    assert "cards" in data


def test_api_cards_by_tags_invalid_logic(client):
    """Test that invalid logic parameter returns error."""
    response = client.get("/api/cards/by-tags?tags=tokens&logic=INVALID&limit=10")
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data


def test_api_cards_by_tags_empty_tags(client):
    """Test that empty tags parameter returns error."""
    response = client.get("/api/cards/by-tags?tags=&logic=AND&limit=10")
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data


def test_api_tags_search(client):
    """Test tag search autocomplete endpoint."""
    response = client.get("/api/cards/tags/search?q=life&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "query" in data
    assert data["query"] == "life"
    assert "matches" in data
    assert isinstance(data["matches"], list)
    
    # Check match structure
    if data["matches"]:
        match = data["matches"][0]
        assert "tag" in match
        assert "card_count" in match
        assert match["tag"].lower().startswith("life")


def test_api_tags_search_min_length(client):
    """Test that tag search requires minimum 2 characters."""
    response = client.get("/api/cards/tags/search?q=a&limit=10")
    
    # Should fail validation
    assert response.status_code == 422


def test_api_tags_popular(client):
    """Test popular tags endpoint."""
    response = client.get("/api/cards/tags/popular?limit=20")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "count" in data
    assert "tags" in data
    assert isinstance(data["tags"], list)
    assert data["count"] == len(data["tags"])
    assert data["count"] <= 20
    
    # Check tag structure
    if data["tags"]:
        tag = data["tags"][0]
        assert "tag" in tag
        assert "card_count" in tag
        assert isinstance(tag["card_count"], int)
        
        # Tags should be sorted by card count (descending)
        if len(data["tags"]) > 1:
            assert data["tags"][0]["card_count"] >= data["tags"][1]["card_count"]


def test_api_tags_popular_limit(client):
    """Test that popular tags endpoint respects limit."""
    response = client.get("/api/cards/tags/popular?limit=5")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["tags"]) <= 5


def test_commanders_page_loads(client):
    """Test that commanders page loads successfully."""
    response = client.get("/commanders")
    
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    
    content = response.text
    # Should have the theme filter input
    assert "commander-theme" in content
    assert "theme-suggestions" in content


def test_commanders_page_with_theme_filter(client):
    """Test commanders page with theme query parameter."""
    response = client.get("/commanders?theme=tokens")
    
    assert response.status_code == 200
    content = response.text
    
    # Should have the theme value in the input
    assert 'value="tokens"' in content or "tokens" in content


@pytest.mark.skip(reason="Performance test - run manually")
def test_theme_autocomplete_performance(client):
    """Test that theme autocomplete responds quickly."""
    import time
    
    start = time.time()
    response = client.get("/commanders/theme-autocomplete?theme=to&limit=20")
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 0.05  # Should respond in <50ms


@pytest.mark.skip(reason="Performance test - run manually")
def test_api_tags_search_performance(client):
    """Test that tag search responds quickly."""
    import time
    
    start = time.time()
    response = client.get("/api/cards/tags/search?q=to&limit=20")
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 0.05  # Should respond in <50ms
