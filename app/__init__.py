import os
from flask import Flask
from dotenv import load_dotenv

# Load environment variables from .env in the project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))


def create_app():
    """Create and configure the Flask application"""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'),
    )

    # Application config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'case-resubmit-dev-secret')
    app.config['DEBUG'] = os.environ.get('DEBUG', 'True').lower() == 'true'
    app.config['Environment'] = os.environ.get('Environment', 'ENV3')

    # Login credentials (dummy values – update via .env for production)
    app.config['APP_USERNAME'] = os.environ.get('APP_USERNAME', 'admin')
    app.config['APP_PASSWORD'] = os.environ.get('APP_PASSWORD', 'admin123')

    # Register blueprints
    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
