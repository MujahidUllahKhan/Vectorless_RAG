"""
Vectorless RAG System
=====================
A hierarchical tree-based RAG system using LLM reasoning instead of vector embeddings.
"""

from .vectorless_rag import (
    VectorlessRAG,
    TreeNode,
    PDFProcessor,
    TreeBuilder,
    LLMTreeSearcher
)

from .supervised_rag import (
    SupervisedRAGEvaluator,
    SupervisedQAPair,
    RetrievalMetrics,
    AnswerMetrics,
    DomainRuleLearner
)

__version__ = "1.0.0"

__all__ = [
    # Main classes
    'VectorlessRAG',
    'SupervisedRAGEvaluator',
    
    # Data structures
    'TreeNode',
    'SupervisedQAPair',
    'RetrievalMetrics',
    'AnswerMetrics',
    
    # Components
    'PDFProcessor',
    'TreeBuilder',
    'LLMTreeSearcher',
    'DomainRuleLearner',
]
