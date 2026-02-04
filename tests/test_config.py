from jm_api.core.config import Settings


def test_database_url_default():
    settings = Settings()
    assert settings.database_url == "sqlite:///./app.db"
