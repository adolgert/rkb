"""Tests for Ollama embedder."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from rkb.embedders.ollama_embedder import OllamaEmbedder


class TestOllamaEmbedder:
    """Tests for OllamaEmbedder."""

    def test_embedder_initialization(self):
        """Test embedder initialization with default values."""
        embedder = OllamaEmbedder()

        assert embedder.model == "mxbai-embed-large"
        assert embedder.base_url == "http://localhost:11434"
        assert embedder.timeout == 30
        assert embedder.batch_size == 100

    def test_embedder_initialization_with_params(self):
        """Test embedder initialization with custom parameters."""
        embedder = OllamaEmbedder(
            model="nomic-embed-text",
            base_url="http://example.com:8080",
            timeout=60,
            batch_size=50,
        )

        assert embedder.model == "nomic-embed-text"
        assert embedder.base_url == "http://example.com:8080"
        assert embedder.timeout == 60
        assert embedder.batch_size == 50

    def test_properties(self):
        """Test embedder properties."""
        embedder = OllamaEmbedder()

        assert embedder.name == "ollama"
        assert embedder.version == "1.0.0"

    def test_get_capabilities(self):
        """Test get_capabilities method."""
        embedder = OllamaEmbedder()
        capabilities = embedder.get_capabilities()

        assert capabilities["name"] == "ollama"
        assert capabilities["description"]
        assert "mxbai-embed-large" in capabilities["supported_models"]
        assert "batch_processing" in capabilities["features"]
        assert "model" in capabilities["configuration"]

    def test_embed_empty_texts(self):
        """Test embedding empty text list."""
        embedder = OllamaEmbedder()
        result = embedder.embed([])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert result.embedder_name == "ollama"

    @patch("requests.post")
    def test_embed_successful(self, mock_post):
        """Test successful embedding generation."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        embedder = OllamaEmbedder()
        result = embedder.embed(["test text", "another text"])

        assert len(result.embeddings) == 2
        assert result.embeddings[0] == [0.1, 0.2, 0.3]
        assert result.chunk_count == 2
        assert result.embedder_name == "ollama"
        assert mock_post.call_count == 2  # One call per text

    @patch("requests.post")
    def test_embed_connection_error(self, mock_post):
        """Test embedding with connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        embedder = OllamaEmbedder()
        result = embedder.embed(["test text"])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert "Cannot connect to Ollama service" in result.error_message

    @patch("requests.post")
    def test_embed_timeout_error(self, mock_post):
        """Test embedding with timeout error."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timeout")

        embedder = OllamaEmbedder()
        result = embedder.embed(["test text"])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert "timed out" in result.error_message

    @patch("requests.post")
    def test_embed_http_error(self, mock_post):
        """Test embedding with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.side_effect = requests.exceptions.HTTPError(response=mock_response)

        embedder = OllamaEmbedder()
        result = embedder.embed(["test text"])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert "HTTP error: 500" in result.error_message

    @patch("requests.post")
    def test_embed_invalid_response(self, mock_post):
        """Test embedding with invalid response format."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "No embedding field"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        embedder = OllamaEmbedder()
        result = embedder.embed(["test text"])

        assert result.embeddings == []
        assert result.chunk_count == 0
        assert "No embedding in response" in result.error_message

    @patch("requests.post")
    def test_embed_single_successful(self, mock_post):
        """Test successful single text embedding."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        embedder = OllamaEmbedder()
        embedding = embedder.embed_single("test text")

        assert embedding == [0.1, 0.2, 0.3]

    @patch("requests.post")
    def test_embed_single_error(self, mock_post):
        """Test single text embedding with error."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        embedder = OllamaEmbedder()
        with pytest.raises(RuntimeError, match="Cannot connect to Ollama service"):
            embedder.embed_single("test text")

    @patch("requests.post")
    def test_test_connection_success(self, mock_post):
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        embedder = OllamaEmbedder()
        assert embedder.test_connection() is True

    @patch("requests.post")
    def test_test_connection_failure(self, mock_post):
        """Test failed connection test."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        embedder = OllamaEmbedder()
        assert embedder.test_connection() is False

    @patch("requests.post")
    def test_batch_processing(self, mock_post):
        """Test batch processing with large text list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Test with batch size of 2
        embedder = OllamaEmbedder(batch_size=2)
        result = embedder.embed(["text1", "text2", "text3"])

        assert len(result.embeddings) == 3
        assert result.chunk_count == 3
        # Should make 3 calls (2 in first batch, 1 in second batch)
        assert mock_post.call_count == 3