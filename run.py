#!/usr/bin/env python
import os
import sys
import logging
from datetime import datetime

from flask import request

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app

app = create_app()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(),
    ],
)

logging.info('Case Resubmit Application started.')


@app.context_processor
def inject_globals():
    return {'now': datetime.now()}


@app.before_request
def log_request():
    logging.info(f'Request: {request.method} {request.url}')


def main():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == '__main__':
    main()
