"""
IMPROVED Vectorless RAG - Better Chunking
==========================================
This version uses smarter chunking based on page content
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
import re

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

UPLOAD_FOLDER = Path('uploads')
CACHE_FOLDER = Path('cache')
UPLOAD_FOLDER.mkdir(exist_ok=True)
CACHE_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

document_cache = {}

GROQ_API_KEY = os.getenv('GROQ_API_KEY') or os.getenv('LLM_API_KEY')
MODEL = os.getenv('LLM_MODEL', 'llama-3.3-70b-versatile')

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("✅ Groq API configured")
else:
    groq_client = None
    print("⚠️ Warning: GROQ_API_KEY not set")


def extract_pdf_with_structure(pdf_path):
    """Extract PDF with better page-level structure detection"""
    pages_data = []
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        num_pages = len(pdf_reader.pages)
        
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            
            # Detect potential section headers (simple heuristic)
            lines = text.split('\n')
            potential_headers = []
            
            for i, line in enumerate(lines[:10]):  # Check first 10 lines
                line = line.strip()
                # Detect headers: short lines, numbers, or all caps
                if line and (
                    len(line) < 50 and 
                    (line[0].isdigit() or line.isupper() or 
                     re.match(r'^\d+\.?\s+[A-Z]', line))
                ):
                    potential_headers.append(line)
            
            pages_data.append({
                'page': page_num + 1,
                'text': text,
                'headers': potential_headers[:3]  # Top 3 potential headers
            })
    
    return pages_data, num_pages


def smart_chunk_by_sections(pages_data, groq_client):
    """
    Use LLM to detect sections and create smart chunks
    This is a simplified version of PageIndex approach
    """
    
    # Build a map of sections
    print("🔍 Detecting document structure...")
    
    # For short docs (<30 pages), just use page-based chunks
    if len(pages_data) <= 30:
        chunks = []
        for page in pages_data:
            chunks.append({
                'id': f'page_{page["page"]}',
                'title': f'Page {page["page"]}' + 
                         (f': {page["headers"][0]}' if page["headers"] else ''),
                'pages': str(page["page"]),
                'text': page["text"]
            })
        return chunks
    
    # For longer docs, group by major sections
    # This is where PageIndex does sophisticated TOC extraction
    # We'll do a simplified version
    
    chunks = []
    current_chunk = []
    current_title = None
    start_page = 1
    
    for i, page in enumerate(pages_data):
        # Check if this page starts a new section
        if page['headers'] and len(current_chunk) > 0:
            # Save previous chunk
            text = '\n\n'.join([p['text'] for p in current_chunk])
            chunks.append({
                'id': f'section_{len(chunks)+1}',
                'title': current_title or f'Section {len(chunks)+1}',
                'pages': f'{start_page}-{current_chunk[-1]["page"]}',
                'text': text
            })
            # Start new chunk
            current_chunk = [page]
            current_title = page['headers'][0]
            start_page = page['page']
        else:
            current_chunk.append(page)
            if not current_title and page['headers']:
                current_title = page['headers'][0]
    
    # Add final chunk
    if current_chunk:
        text = '\n\n'.join([p['text'] for p in current_chunk])
        chunks.append({
            'id': f'section_{len(chunks)+1}',
            'title': current_title or f'Section {len(chunks)+1}',
            'pages': f'{start_page}-{current_chunk[-1]["page"]}',
            'text': text
        })
    
    return chunks


def search_with_reasoning(query, chunks, groq_client, top_k=3):
    """
    Two-step search like PageIndex:
    1. First pass: Find relevant sections by title/summary
    2. Second pass: Deep search in selected sections
    """
    
    # Step 1: Quick scan of all chunks
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        summary = f"{i+1}. {chunk['title']} (Pages {chunk['pages']})"
        chunk_summaries.append(summary)
    
    summaries_text = '\n'.join(chunk_summaries)
    
    prompt1 = f"""You are analyzing a document to find relevant sections.

DOCUMENT STRUCTURE:
{summaries_text}

QUESTION: {query}

Which sections are most relevant? Consider:
1. Does the section title suggest it contains the answer?
2. Which pages are most likely to have this information?

Return ONLY a JSON array of section numbers (e.g., [1, 5, 7]).
Example: {{"sections": [1, 3]}}

JSON:"""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt1}],
            temperature=0
        )
        
        result_text = response.choices[0].message.content.strip()
        result_text = result_text.replace('```json', '').replace('```', '').strip()
        
        result = json.loads(result_text)
        section_nums = result.get('sections', [1, 2, 3])
        
        # Get selected chunks
        selected = [chunks[i-1] for i in section_nums if 0 < i <= len(chunks)]
        
        print(f"📍 Selected sections: {section_nums} - {[c['title'] for c in selected]}")
        
        return selected[:top_k]
    
    except Exception as e:
        print(f"Error in reasoning search: {e}")
        return chunks[:top_k]


def generate_answer(query, relevant_chunks, groq_client):
    """Generate answer with better context"""
    
    context = "\n\n---\n\n".join([
        f"**{chunk['title']}** (Pages {chunk['pages']}):\n{chunk['text'][:2000]}"
        for chunk in relevant_chunks
    ])
    
    prompt = f"""Answer the question using ONLY the provided context. Be specific and cite page numbers.

CONTEXT:
{context}

QUESTION: {query}

Provide a clear, detailed answer with specific page citations.

ANSWER:"""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"Error: {e}"


# ... (rest of Flask routes stay the same, but use new functions)


@app.route('/')
def serve_frontend():
    return send_from_directory('frontend', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'groq_configured': bool(GROQ_API_KEY),
        'model': MODEL,
        'documents': len(document_cache),
        'version': 'improved_chunking'
    })


@app.route('/api/index', methods=['POST'])
def index_document():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are supported'}), 400
        
        if not GROQ_API_KEY:
            return jsonify({'error': 'Groq API key not configured'}), 500
        
        doc_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        file_path = UPLOAD_FOLDER / f"{doc_id}_{filename}"
        
        file.save(file_path)
        
        print(f"📄 Processing: {filename}")
        
        # Extract with structure detection
        pages_data, num_pages = extract_pdf_with_structure(file_path)
        
        # Create smart chunks
        chunks = smart_chunk_by_sections(pages_data, groq_client)
        
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
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/query', methods=['POST'])
def query_documents():
    try:
        data = request.get_json()
        
        if not data or 'question' not in data:
            return jsonify({'error': 'No question provided'}), 400
        
        question = data['question']
        
        if not document_cache:
            return jsonify({'error': 'No documents indexed'}), 400
        
        if not GROQ_API_KEY:
            return jsonify({'error': 'Groq API key not configured'}), 500
        
        doc_id = list(document_cache.keys())[-1]
        doc_data = document_cache[doc_id]
        
        print(f"❓ Query: {question}")
        
        # Use reasoning-based search
        relevant_chunks = search_with_reasoning(
            question, 
            doc_data['chunks'],
            groq_client,
            top_k=3
        )
        
        # Generate answer
        answer = generate_answer(question, relevant_chunks, groq_client)
        
        sources = [
            {
                'title': chunk['title'],
                'pages': chunk['pages'],
                'document': doc_data['filename']
            }
            for chunk in relevant_chunks
        ]
        
        steps = [
            {
                'title': 'Structure Analysis',
                'description': f'Analyzed {len(doc_data["chunks"])} sections in document structure',
                'nodes': [
                    {
                        'id': chunk['id'],
                        'title': chunk['title'],
                        'pages': chunk['pages']
                    }
                    for chunk in relevant_chunks
                ]
            },
            {
                'title': 'Reasoning-Based Retrieval',
                'description': f'Selected {len(relevant_chunks)} most relevant sections using LLM reasoning'
            },
            {
                'title': 'Answer Generation',
                'description': 'Generated answer with citations using Groq LLM'
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
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents', methods=['GET'])
def list_documents():
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
    print("IMPROVED VECTORLESS RAG - GROQ VERSION")
    print("=" * 80)
    print(f"Model: {MODEL}")
    print(f"Groq API: {'✅ Configured' if GROQ_API_KEY else '❌ Not configured'}")
    print("Features: Smart chunking, Reasoning-based retrieval")
    print("=" * 80)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
