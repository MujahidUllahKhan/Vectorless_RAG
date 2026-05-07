"""
Simple Example: Vectorless RAG System
======================================
This script demonstrates basic usage of the vectorless RAG system.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / 'src'))

from vectorless_rag import VectorlessRAG
from supervised_rag import SupervisedRAGEvaluator
from dotenv import load_dotenv


def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found in .env file")
        print("   Please copy .env.example to .env and add your API key")
        return
    
    print("="*80)
    print("VECTORLESS RAG SYSTEM - EXAMPLE")
    print("="*80)
    
    # Initialize RAG system
    print("\n📦 Initializing RAG system...")
    rag = VectorlessRAG(openai_api_key=api_key)
    print("✅ RAG system ready")
    
    # Check for PDF file
    pdf_path = "data/sample_document.pdf"
    if not os.path.exists(pdf_path):
        print(f"\n⚠️ PDF file not found: {pdf_path}")
        print("   Please place your PDF in the data/ folder")
        print("   You can use any research paper, report, or manual")
        return
    
    # Index document
    print(f"\n📄 Indexing document: {pdf_path}")
    print("   This may take 1-2 minutes...")
    
    cache_path = "data/sample_document_tree.json"
    tree = rag.index_document(
        pdf_path=pdf_path,
        cache_path=cache_path,
        max_pages_per_node=10,
        generate_summaries=True
    )
    
    print("✅ Document indexed!")
    
    # Show tree structure
    print("\n🌲 Document Structure:")
    print("-"*80)
    rag.print_tree()
    print("-"*80)
    
    # Example queries
    queries = [
        "What is the main topic of this document?",
        "What methodology or approach is used?",
        "What are the key findings or results?"
    ]
    
    print("\n" + "="*80)
    print("RUNNING EXAMPLE QUERIES")
    print("="*80)
    
    for i, query in enumerate(queries, 1):
        print(f"\n[Query {i}/{len(queries)}]")
        print(f"❓ {query}")
        print("-"*80)
        
        result = rag.query(query, max_nodes=3)
        
        print(f"\n📝 Answer:")
        print(result['answer'])
        
        print(f"\n📚 Sources:")
        for source in result['sources']:
            print(f"  • {source['title']} (pages {source['pages']})")
        print()
    
    # Supervised evaluation example
    print("\n" + "="*80)
    print("SUPERVISED EVALUATION EXAMPLE")
    print("="*80)
    
    evaluator = SupervisedRAGEvaluator(openai_client=rag.client)
    
    # Load example QA dataset
    qa_path = "supervised/example_qa_dataset.json"
    if os.path.exists(qa_path):
        print(f"\n📂 Loading QA dataset: {qa_path}")
        evaluator.load_qa_pairs(qa_path)
        
        print(f"\n🔬 Running evaluation on {len(evaluator.qa_pairs)} QA pairs...")
        print("   (This may take a few minutes)")
        
        results = evaluator.evaluate_rag_system(rag, verbose=False)
        
        print("\n" + "="*80)
        print("EVALUATION RESULTS")
        print("="*80)
        print(results['aggregate_metrics']['summary'])
    else:
        print(f"\n⚠️ QA dataset not found: {qa_path}")
        print("   Skipping evaluation")
    
    print("\n" + "="*80)
    print("✅ EXAMPLE COMPLETE!")
    print("="*80)
    print("\nNext steps:")
    print("  1. Try with your own PDF documents")
    print("  2. Create custom QA datasets for your domain")
    print("  3. Add domain-specific rules to improve retrieval")
    print("  4. See notebooks/tutorial.ipynb for detailed explanations")
    print()


if __name__ == "__main__":
    main()
