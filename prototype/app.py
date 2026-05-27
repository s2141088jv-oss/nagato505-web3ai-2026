from flask import Flask, render_template, request, jsonify
import requests
import xml.etree.ElementTree as ET
from deep_translator import GoogleTranslator
from datetime import datetime, timezone
import re
import os

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)

ARXIV_NS = '{http://www.w3.org/2005/Atom}'


def search_arxiv(query, max_results=4):
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": " AND ".join(f"all:{w}" for w in query.split()),
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        return parse_arxiv_response(response.text)
    except Exception as e:
        app.logger.error(f"arXiv fetch error: {e}")
        return []


def parse_arxiv_response(xml_text):
    papers = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for entry in root.findall(f'{ARXIV_NS}entry'):
        title_elem = entry.find(f'{ARXIV_NS}title')
        summary_elem = entry.find(f'{ARXIV_NS}summary')
        published_elem = entry.find(f'{ARXIV_NS}published')
        id_elem = entry.find(f'{ARXIV_NS}id')

        if None in (title_elem, summary_elem, published_elem, id_elem):
            continue

        paper = {
            'id': id_elem.text.strip(),
            'title': title_elem.text.strip().replace('\n', ' '),
            'abstract': summary_elem.text.strip().replace('\n', ' '),
            'published': published_elem.text.strip(),
            'authors': [
                a.find(f'{ARXIV_NS}name').text
                for a in entry.findall(f'{ARXIV_NS}author')
                if a.find(f'{ARXIV_NS}name') is not None
            ],
            'url': id_elem.text.strip(),
        }
        for link in entry.findall(f'{ARXIV_NS}link'):
            if link.get('rel') == 'alternate':
                paper['url'] = link.get('href', paper['url'])

        papers.append(paper)

    return papers


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


def priority_stars(index, pub_date_str):
    try:
        pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
        days_old = (datetime.now(timezone.utc) - pub_date).days
        recency = 1 if days_old < 365 else (0.5 if days_old < 730 else 0)
    except Exception:
        recency = 0

    relevance = max(0, 1 - index * 0.15)
    score = relevance + recency * 0.3

    if score > 1.1:
        return 3
    elif score > 0.7:
        return 2
    else:
        return 1


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

    papers = search_arxiv(query)
    if not papers:
        return jsonify({'error': 'arXivから論文が見つかりませんでした。キーワードを変えてみてください。'}), 404

    results = []
    for i, paper in enumerate(papers):
        title_ja = translate_to_japanese(paper['title'])
        abstract_ja = translate_to_japanese(get_short_abstract(paper['abstract']))

        results.append({
            'rank': i + 1,
            'title_en': paper['title'],
            'title_ja': title_ja,
            'abstract_ja': abstract_ja,
            'authors': paper['authors'][:3],
            'published': paper['published'][:4],
            'url': paper['url'],
            'stars': priority_stars(i, paper['published']),
        })

    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
