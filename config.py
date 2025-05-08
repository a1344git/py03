import os

class Config:
    """共通設定"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    UPLOAD_FOLDER = '/tmp/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

class DevelopmentConfig(Config):
    """開発環境設定"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """テスト環境設定"""
    DEBUG = False
    TESTING = True

class ProductionConfig(Config):
    """本番環境設定"""
    DEBUG = False
    TESTING = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    JSONIFY_PRETTYPRINT_REGULAR = False

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
