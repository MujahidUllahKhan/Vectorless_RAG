"""
Flask API Server for Vectorless RAG System with Groq
====================================================
This version works with Groq free API
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
from pathlib import Path
from datetime import datetime
import PyPDF2
from groq import Groq

# Initialize Flask app
app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

# Configuration
UPLOAD_FOLDER = Path('uploads')
CACHE_FOLDER = Path('cache')
UPLOAD_FOLDER.mkdir(exist_ok=True)
CACHE_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Global state
document_cache = {}

# Get Groq API key
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or os.getenv('LLM_API_KEY')
MODEL = os.getenv('LLM_MODEL', 'llama-3.3-70b-versatile')

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✅ Groq API configured")
else:
    groq_client = None
    print("⚠️ Warning: GROQ_API_KEY not set")


def extract_pdf_text(pdf_path):
    """Extract all text from PDF"""
    text_by_page = []
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        num_pages = len(pdf_reader.pages)
        
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            text_by_page.append({
                'page': page_num + 1,
                'text': text
            })
    
    return text_by_page, num_pages


def simple_chunk_text(pages_data, chunk_size=5):
    """Create simple chunks from pages"""
    chunks = []
    
    for i in range(0, len(pages_data), chunk_size):
        chunk_pages = pages_data[i:i + chunk_size]
        
        combined_text = '\n\n'.join([
            f"[Page {p['page']}]\n{p['text']}" 
            for p in chunk_pages
        ])
        
        chunks.append({
            'id': f'chunk_{i//chunk_size + 1}',
            'pages': f"{chunk_pages[0]['page']}-{chunk_pages[-1]['page']}",
            'text': combined_text
        })
    
    return chunks


def search_relevant_chunks(query, chunks, groq_client, top_k=3):
    """Use Groq to find relevant chunks"""
    
    # Create a summary of all chunks for the LLM
    chunk_summaries = "\n\n".join([
        f"Chunk {i+1} (Pages {c['pages']}):\n{c['text'][:500]}..."
        for i, c in enumerate(chunks)
    ])
    
    prompt = f"""You are analyzing a document to find relevant sections.

AVAILABLE CHUNKS:
{chunk_summaries}

USER QUESTION: {query}

Which chunks are most relevant to answer this question? Respond with ONLY a JSON array of chunk numbers (1-indexed).
Example: {{"relevant_chunks": [1, 3, 5]}}

Respond ONLY with valid JSON."""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        result_text = response.choices[0].message.content.strip()
        # Clean markdown if present
        result_text = result_text.replace('```json', '').replace('```', '').strip()
        
        result = json.loads(result_text)
        chunk_indices = result.get('relevant_chunks', [1, 2, 3])
        
        # Get the actual chunks
        relevant = [chunks[i-1] for i in chunk_indices if 0 < i <= len(chunks)]
        return relevant[:top_k]
    
    except Exception as e:
        print(f"Error in search: {e}")
        # Fallback: return first few chunks
        return chunks[:top_k]


def generate_answer(query, relevant_chunks, groq_client):
    """Generate answer from relevant chunks"""
    
    context = "\n\n".join([
        f"SOURCE: Pages {chunk['pages']}\n{chunk['text']}"
        for chunk in relevant_chunks
    ])
    
    prompt = f"""Answer the question using ONLY the provided context. Include specific page citations.

CONTEXT FROM DOCUMENT:
{context}

QUESTION: {query}

Provide a clear answer with citations to specific page numbers.

ANSWER:"""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"Error generating answer: {str(e)}"


@app.route('/')
def serve_frontend():
    """Serve the frontend HTML"""
    return send_from_directory('frontend', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'groq_configured': bool(GROQ_API_KEY),
        'model': MODEL,
        'documents': len(document_cache)
    })


@app.route('/api/index', methods=['POST'])
def index_document():
    """Index a PDF document"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are supported'}), 400
        
        if not GROQ_API_KEY:
            return jsonify({'error': 'Groq API key not configured'}), 500
        
        # Generate document ID
        doc_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        file_path = UPLOAD_FOLDER / f"{doc_id}_{filename}"
        
        # Save file
        file.save(file_path)
        
        print(f"📄 Processing: {filename}")
        
        # Extract text from PDF
        pages_data, num_pages = extract_pdf_text(file_path)
        
        # Create chunks
        chunks = simple_chunk_text(pages_data)
        
        # Store in cache
        document_cache[doc_id] = {
            'filename': filename,
            'num_pages': num_pages,
            'chunks': chunks,
            'indexed_at': datetime.now().isoformat()
        }
        
        print(f"✅ Indexed: {filename} ({num_pages} pages, {len(chunks)} chunks)")
        
        return jsonify({
            'doc_id': doc_id,
            'filename': filename,
            'num_pages': num_pages,
            'num_nodes': len(chunks),
            'status': 'ready',
            'message': f'Successfully indexed {filename}'
        })
    
    except Exception as e:
        print(f"❌ Error indexing: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/query', methods=['POST'])
def query_documents():
    """Query indexed documents"""
    try:
        data = request.get_json()
        
        if not data or 'question' not in data:
            return jsonify({'error': 'No question provided'}), 400
        
        question = data['question']
        
        if not document_cache:
            return jsonify({'error': 'No documents indexed'}), 400
        
        if not GROQ_API_KEY:
            return jsonify({'error': 'Groq API key not configured'}), 500
        
        # Use the most recent document
        doc_id = list(document_cache.keys())[-1]
        doc_data = document_cache[doc_id]
        
        print(f"❓ Query: {question}")
        
        # Search for relevant chunks
        relevant_chunks = search_relevant_chunks(
            question, 
            doc_data['chunks'],
            groq_client,
            top_k=3
        )
        
        # Generate answer
        answer = generate_answer(question, relevant_chunks, groq_client)
        
        # Format response
        sources = [
            {
                'title': f"Chunk {chunk['id']}",
                'pages': chunk['pages'],
                'document': doc_data['filename']
            }
            for chunk in relevant_chunks
        ]
        
        steps = [
            {
                'title': 'Document Search',
                'description': f'Searched {len(doc_data["chunks"])} chunks from {doc_data["filename"]}',
                'nodes': [
                    {
                        'id': chunk['id'],
                        'title': f"Chunk {chunk['id']}",
                        'pages': chunk['pages']
                    }
                    for chunk in relevant_chunks
                ]
            },
            {
                'title': 'Content Retrieval',
                'description': f'Retrieved {len(relevant_chunks)} relevant chunks'
            },
            {
                'title': 'Answer Generation',
                'description': 'Generated answer using Groq LLM with citations'
            }
        ]
        
        print(f"✅ Answer generated")
        
        return jsonify({
            'answer': answer,
            'sources': sources,
            'steps': steps,
            'doc_id': doc_id,
            'llm_provider': 'groq',
            'llm_model': MODEL
        })
    
    except Exception as e:
        print(f"❌ Error in query: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents', methods=['GET'])
def list_documents():
    """List all indexed documents"""
    docs = [
        {
            'doc_id': doc_id,
            'filename': data['filename'],
            'num_pages': data['num_pages'],
            'num_nodes': len(data['chunks']),
            'indexed_at': data['indexed_at'],
            'status': 'ready'
        }
        for doc_id, data in document_cache.items()
    ]
    
    return jsonify({
        'documents': docs,
        'total': len(docs)
    })


if __name__ == '__main__':
    print("=" * 80)
    print("VECTORLESS RAG - GROQ VERSION")
    print("=" * 80)
    print(f"Model: {MODEL}")
    print(f"Groq API: {'✅ Configured' if GROQ_API_KEY else '❌ Not configured'}")
    print("=" * 80)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
