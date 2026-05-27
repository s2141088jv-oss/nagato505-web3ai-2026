from flask import Flask, render_template, request, jsonify
import requests
from deep_translator import GoogleTranslator
from datetime import datetime
import re
import os

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)

OPENALEX_URL = "https://api.openalex.org/works"
HEADERS = {"User-Agent": "PaperResearchAssistant/1.0 (mailto:s2141088jv@chibatech.ac.jp)"}


def search_papers(query, max_results=4):
    params = {
        "search": query,
        "per-page": max_results,
        "select": "id,title,abstract_inverted_index,authorships,publication_year,doi,primary_location",
        "mailto": "s2141088jv@chibatech.ac.jp",
    }
    try:
        response = requests.get(OPENALEX_URL, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        app.logger.error(f"OpenAlex fetch error: {e}")
        return []


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    pos_word = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            pos_word[pos] = word
    return " ".join(pos_word[i] for i in sorted(pos_word))


def translate_to_japanese(text):
    if not text or len(text.strip()) < 5:
        return text
    if len(text) > 4500:
        text = text[:4500]
    try:
        result = GoogleTranslator(source='auto', target='ja').translate(text)
        return result if result else text
    except Exception:
        return text


def get_short_abstract(abstract, num_sentences=4):
    sentences = re.split(r'(?<=[.!?])\s+', abstract)
    short = ' '.join(sentences[:num_sentences])
    return short[:500] + ('...' if len(short) > 500 else '')


def priority_stars(index, year):
    current_year = datetime.now().year
    age = current_year - (year or current_year)
    recency = 1 if age <= 1 else (0.5 if age <= 3 else 0)
    relevance = max(0, 1 - index * 0.2)
    score = relevance + recency * 0.3
    if score > 1.1:
        return 3
    elif score > 0.6:
        return 2
    else:
        return 1


def paper_url(raw):
    if raw.get("doi"):
        return raw["doi"]
    loc = raw.get("primary_location") or {}
    return loc.get("landing_page_url") or raw.get("id") or "https://openalex.org"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'リクエストが不正です'}), 400

    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': '検索キーワードを入力してください'}), 400

    papers = search_papers(query)
    if not papers:
        return jsonify({'error': '論文が見つかりませんでした。別のキーワードを試してください。'}), 404

    results = []
    for i, p in enumerate(papers):
        title = (p.get('title') or '').replace('\n', ' ')
        abstract_raw = reconstruct_abstract(p.get('abstract_inverted_index'))
        year = p.get('publication_year')
        authors = [
            a['author']['display_name']
            for a in (p.get('authorships') or [])[:3]
            if a.get('author', {}).get('display_name')
        ]

        title_ja = translate_to_japanese(title)
        abstract_ja = translate_to_japanese(get_short_abstract(abstract_raw)) if abstract_raw else '（要旨なし）'

        results.append({
            'rank': i + 1,
            'title_en': title,
            'title_ja': title_ja,
            'abstract_ja': abstract_ja,
            'authors': authors,
            'published': str(year) if year else '不明',
            'url': paper_url(p),
            'stars': priority_stars(i, year),
        })

    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
