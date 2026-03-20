from flask import Flask, request, jsonify, redirect
from systems import Ranker
from flask_cors import CORS

import os 

# Read the retrieval model from the environment, if provided
WMODEL = os.getenv('WMODEL')

app = Flask(__name__)
# Allow the search API to be called from other services/ports
CORS(app)

# Create one shared ranker instance for indexing and retrieval
ranker = Ranker(wmodel=WMODEL)


@app.route('/')
def redirect_to_test():
    # Redirect root requests to a simple health-check endpoint
    return redirect("/test", code=302)


@app.route('/test', methods=["GET"])
def test():
    # Lightweight endpoint to verify that the container is running
    return 'Container is running', 200


@app.route('/index', methods=["GET"])
def index():
    # Build the search index from the configured corpus
    ranker.index()
    return 'Indexing done!', 200


@app.route('/ranking', methods=["GET"])
def ranking():
    # Read ranking parameters from the query string
    query = request.args.get('query', None)
    page = request.args.get('page', default=0, type=int)
    rpp = request.args.get('rpp', default=20, type=int)

    # Delegate retrieval to the Ranker and return JSON results
    response = ranker.rank_publications(query, page, rpp)
    return jsonify(response)


if __name__ == '__main__':
    # Run the search engine service
    app.run(host='0.0.0.0', port=7002, debug=False, threaded=True)