"""
Flask API Server for Vectorless RAG System
==========================================
Provides REST API endpoints for the frontend chatbot
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add backend src to path
sys.path.append(str(Path(__file__).parent / 'backend' / 'src'))

from vectorless_rag import VectorlessRAG, TreeNode
from supervised_rag import SupervisedRAGEvaluator

# Initialize Flask app
app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

# Configuration
UPLOAD_FOLDER = Path('uploads')
CACHE_FOLDER = Path('cache')
UPLOAD_FOLDER.mkdir(exist_ok=True)
CACHE_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Global state
rag_systems = {}  # doc_id -> RAG instance
document_metadata = {}  # doc_id -> metadata

# Initialize RAG with API key from environment
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    print("⚠️ Warning: OPENAI_API_KEY not set in environment")


@app.route('/')
def serve_frontend():
    """Serve the frontend HTML"""
    return send_from_directory('frontend', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'documents_indexed': len(rag_systems),
        'api_key_configured': bool(OPENAI_API_KEY)
    })


@app.route('/api/index', methods=['POST'])
def index_document():
    """
    Index a PDF document
    
    Request:
        - file: PDF file upload
        - generate_summaries: bool (optional, default True)
        - max_pages_per_node: int (optional, default 10)
    
    Response:
        {
            'doc_id': str,
            'filename': str,
            'status': 'indexing',
            'message': str
        }
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are supported'}), 400
        
        # Check API key
        if not OPENAI_API_KEY:
            return jsonify({'error': 'OpenAI API key not configured'}), 500
        
        # Generate document ID
        doc_id = datetime.now().strftime('%Y%m%d_%H%M%S_') + secure_filename(file.filename).replace('.pdf', '')
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = UPLOAD_FOLDER / f"{doc_id}.pdf"
        file.save(file_path)
        
        # Get parameters
        generate_summaries = request.form.get('generate_summaries', 'true').lower() == 'true'
        max_pages_per_node = int(request.form.get('max_pages_per_node', 10))
        
        # Initialize RAG system
        rag = VectorlessRAG(
            openai_api_key=OPENAI_API_KEY,
            model='gpt-4o-mini'
        )
        
        # Index document
        cache_path = CACHE_FOLDER / f"{doc_id}_tree.json"
        
        print(f"📄 Indexing document: {filename}")
        tree = rag.index_document(
            pdf_path=str(file_path),
            cache_path=str(cache_path),
            max_pages_per_node=max_pages_per_node,
            generate_summaries=generate_summaries
        )
        
        # Count nodes and pages
        def count_nodes(node):
            return 1 + sum(count_nodes(child) for child in node.children)
        
        num_nodes = count_nodes(tree)
        num_pages = tree.page_end
        
        # Store RAG system and metadata
        rag_systems[doc_id] = rag
        document_metadata[doc_id] = {
            'doc_id': doc_id,
            'filename': filename,
            'file_path': str(file_path),
            'cache_path': str(cache_path),
            'num_pages': num_pages,
            'num_nodes': num_nodes,
            'indexed_at': datetime.now().isoformat(),
            'status': 'ready'
        }
        
        print(f"✅ Document indexed: {filename} ({num_pages} pages, {num_nodes} nodes)")
        
        return jsonify({
            'doc_id': doc_id,
            'filename': filename,
            'num_pages': num_pages,
            'num_nodes': num_nodes,
            'status': 'ready',
            'message': f'Successfully indexed {filename}'
        })
    
    except Exception as e:
        print(f"❌ Error indexing document: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/query', methods=['POST'])
def query_documents():
    """
    Query indexed documents
    
    Request:
        {
            'question': str,
            'doc_ids': [str] (optional, queries all if not provided),
            'max_nodes': int (optional, default 5),
            'domain_rules': str (optional)
        }
    
    Response:
        {
            'answer': str,
            'sources': [{'title': str, 'pages': str, 'document': str}],
            'steps': [{'title': str, 'description': str, 'nodes': [...]}],
            'query_time': float
        }
    """
    try:
        data = request.get_json()
        
        if not data or 'question' not in data:
            return jsonify({'error': 'No question provided'}), 400
        
        question = data['question']
        max_nodes = data.get('max_nodes', 5)
        domain_rules = data.get('domain_rules')
        doc_ids = data.get('doc_ids')
        
        # If no doc_ids specified, use all indexed documents
        if not doc_ids:
            doc_ids = list(rag_systems.keys())
        
        if not doc_ids:
            return jsonify({'error': 'No documents indexed'}), 400
        
        # For now, query the first document
        # TODO: Implement multi-document querying
        doc_id = doc_ids[0]
        
        if doc_id not in rag_systems:
            return jsonify({'error': f'Document {doc_id} not found'}), 404
        
        rag = rag_systems[doc_id]
        
        print(f"❓ Query: {question}")
        
        # Time the query
        import time
        start_time = time.time()
        
        # Execute query
        result = rag.query(
            question=question,
            max_nodes=max_nodes,
            domain_rules=domain_rules
        )
        
        query_time = time.time() - start_time
        
        # Build detailed steps for frontend visualization
        steps = [
            {
                'title': 'Tree Search',
                'description': f'LLM analyzed document structure and identified {len(result["node_ids"])} relevant sections',
                'nodes': [
                    {
                        'id': node_id,
                        'title': source['title'],
                        'pages': source['pages']
                    }
                    for node_id, source in zip(result['node_ids'], result['sources'])
                ]
            },
            {
                'title': 'Content Retrieval',
                'description': f'Retrieved full text content from {len(result["sources"])} relevant nodes'
            },
            {
                'title': 'Answer Generation',
                'description': 'LLM synthesized answer from retrieved context with citations'
            }
        ]
        
        # Add document name to sources
        doc_filename = document_metadata[doc_id]['filename']
        for source in result['sources']:
            source['document'] = doc_filename
        
        print(f"✅ Answer generated in {query_time:.2f}s")
        
        return jsonify({
            'answer': result['answer'],
            'sources': result['sources'],
            'steps': steps,
            'query_time': query_time,
            'doc_id': doc_id
        })
    
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents', methods=['GET'])
def list_documents():
    """
    List all indexed documents
    
    Response:
        {
            'documents': [
                {
                    'doc_id': str,
                    'filename': str,
                    'num_pages': int,
                    'num_nodes': int,
                    'indexed_at': str,
                    'status': str
                }
            ]
        }
    """
    try:
        documents = list(document_metadata.values())
        return jsonify({
            'documents': documents,
            'total': len(documents)
        })
    
    except Exception as e:
        print(f"❌ Error listing documents: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """
    Delete an indexed document
    
    Response:
        {
            'message': str,
            'doc_id': str
        }
    """
    try:
        if doc_id not in rag_systems:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get metadata
        metadata = document_metadata[doc_id]
        
        # Delete files
        file_path = Path(metadata['file_path'])
        cache_path = Path(metadata['cache_path'])
        
        if file_path.exists():
            file_path.unlink()
        
        if cache_path.exists():
            cache_path.unlink()
        
        # Remove from memory
        del rag_systems[doc_id]
        del document_metadata[doc_id]
        
        print(f"🗑️ Deleted document: {metadata['filename']}")
        
        return jsonify({
            'message': f"Deleted document {metadata['filename']}",
            'doc_id': doc_id
        })
    
    except Exception as e:
        print(f"❌ Error deleting document: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tree/<doc_id>', methods=['GET'])
def get_document_tree(doc_id):
    """
    Get document tree structure
    
    Response:
        {
            'doc_id': str,
            'tree': {...}
        }
    """
    try:
        if doc_id not in rag_systems:
            return jsonify({'error': 'Document not found'}), 404
        
        rag = rag_systems[doc_id]
        tree_dict = rag.tree.to_dict()
        
        return jsonify({
            'doc_id': doc_id,
            'tree': tree_dict
        })
    
    except Exception as e:
        print(f"❌ Error getting tree: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get system statistics
    
    Response:
        {
            'total_documents': int,
            'total_pages': int,
            'total_nodes': int,
            'total_queries': int
        }
    """
    try:
        total_pages = sum(meta['num_pages'] for meta in document_metadata.values())
        total_nodes = sum(meta['num_nodes'] for meta in document_metadata.values())
        
        return jsonify({
            'total_documents': len(document_metadata),
            'total_pages': total_pages,
            'total_nodes': total_nodes,
            'api_configured': bool(OPENAI_API_KEY)
        })
    
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("VECTORLESS RAG API SERVER")
    print("=" * 80)
    print()
    
    if not OPENAI_API_KEY:
        print("⚠️ WARNING: OPENAI_API_KEY not set!")
        print("   Please set the environment variable before indexing documents")
        print()
    else:
        print("✅ OpenAI API key configured")
        print()
    
    print("Server starting on http://localhost:5000")
    print()
    print("API Endpoints:")
    print("  POST   /api/index       - Index a PDF document")
    print("  POST   /api/query       - Query indexed documents")
    print("  GET    /api/documents   - List all documents")
    print("  DELETE /api/documents/<id> - Delete a document")
    print("  GET    /api/tree/<id>   - Get document tree")
    print("  GET    /api/stats       - Get system statistics")
    print("=" * 80)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
