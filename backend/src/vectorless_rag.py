"""
Vectorless RAG System with Hierarchical Tree Indexing
======================================================
This module implements a vector-free RAG system that uses LLM-based reasoning
over document structure instead of embedding similarity search.

Key Concepts:
- Tree Index: Hierarchical representation of document structure
- LLM Tree Search: Reasoning-based retrieval instead of cosine similarity
- No Chunking: Respects natural document boundaries
- Traceable: Clear provenance for every retrieved section
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import PyPDF2
from openai import OpenAI


@dataclass
class TreeNode:
    """
    Represents a node in the document tree structure.
    
    Attributes:
        node_id: Unique identifier for this node
        title: Section/subsection title
        page_start: Starting page number (1-indexed)
        page_end: Ending page number (1-indexed)
        level: Depth in tree (0=root, 1=chapter, 2=section, etc.)
        summary: Optional LLM-generated summary of this section
        content: Actual text content of this section
        children: List of child nodes
    """
    node_id: str
    title: str
    page_start: int
    page_end: int
    level: int
    summary: Optional[str] = None
    content: Optional[str] = None
    children: List['TreeNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
    
    def to_dict(self) -> Dict:
        """Convert node to dictionary for JSON serialization"""
        return {
            'node_id': self.node_id,
            'title': self.title,
            'page_start': self.page_start,
            'page_end': self.page_end,
            'level': self.level,
            'summary': self.summary,
            'content': self.content,
            'children': [child.to_dict() for child in self.children]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TreeNode':
        """Create node from dictionary"""
        children_data = data.pop('children', [])
        node = cls(**data)
        node.children = [cls.from_dict(child) for child in children_data]
        return node


class PDFProcessor:
    """
    Handles PDF reading and text extraction.
    
    This class is responsible for:
    1. Reading PDF files page by page
    2. Extracting raw text content
    3. Preserving page boundaries for tree construction
    """
    
    @staticmethod
    def extract_pages(pdf_path: str) -> List[Tuple[int, str]]:
        """
        Extract text from PDF page by page.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of (page_number, text_content) tuples
        """
        pages = []
        
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            
            print(f"📄 Extracting {num_pages} pages from PDF...")
            
            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                pages.append((page_num + 1, text))  # 1-indexed pages
        
        print(f"✅ Extracted {len(pages)} pages")
        return pages


class TreeBuilder:
    """
    Constructs hierarchical tree index from document pages using LLM.
    
    The tree building process:
    1. Extract Table of Contents if present
    2. Use LLM to identify section boundaries
    3. Build hierarchical structure respecting document organization
    4. Generate summaries for each node (optional)
    """
    
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
        self.node_counter = 0
    
    def _generate_node_id(self) -> str:
        """Generate unique node ID"""
        self.node_counter += 1
        return f"node_{self.node_counter:04d}"
    
    def build_tree_from_pages(
        self, 
        pages: List[Tuple[int, str]], 
        max_pages_per_node: int = 10,
        generate_summaries: bool = True
    ) -> TreeNode:
        """
        Build hierarchical tree from PDF pages.
        
        Args:
            pages: List of (page_num, text) tuples
            max_pages_per_node: Maximum pages per tree node
            generate_summaries: Whether to generate LLM summaries
            
        Returns:
            Root node of the tree
        """
        print("🌲 Building tree structure...")
        
        # Step 1: Try to extract existing TOC
        toc = self._extract_toc(pages[:20])  # Check first 20 pages
        
        # Step 2: Build tree structure
        if toc:
            print("✅ Found existing Table of Contents")
            root = self._build_from_toc(pages, toc, max_pages_per_node)
        else:
            print("⚠️ No TOC found, using LLM to infer structure")
            root = self._build_with_llm(pages, max_pages_per_node)
        
        # Step 3: Generate summaries if requested
        if generate_summaries:
            print("📝 Generating node summaries...")
            self._add_summaries(root)
        
        print(f"✅ Tree built with {self._count_nodes(root)} nodes")
        return root
    
    def _extract_toc(self, first_pages: List[Tuple[int, str]]) -> Optional[List[Dict]]:
        """
        Use LLM to extract Table of Contents from first pages.
        
        Returns:
            List of TOC entries with {title, page, level} or None
        """
        # Combine first pages
        text = "\n\n".join([f"=== PAGE {p} ===\n{t}" for p, t in first_pages])
        
        prompt = f"""Analyze this document and extract the Table of Contents if present.

Document excerpt:
{text[:8000]}  # Limit to 8K chars

If you find a Table of Contents, extract it as JSON with this format:
[
  {{"title": "Chapter 1: Introduction", "page": 1, "level": 1}},
  {{"title": "1.1 Background", "page": 2, "level": 2}},
  ...
]

Rules:
- level 1 = chapters/main sections
- level 2 = subsections
- level 3 = sub-subsections
- Only include entries that have page numbers

If no TOC exists, respond with: {{"toc": null}}

Respond ONLY with valid JSON."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if isinstance(result, dict) and result.get('toc') is None:
                return None
            
            return result if isinstance(result, list) else result.get('toc')
        
        except Exception as e:
            print(f"⚠️ TOC extraction failed: {e}")
            return None
    
    def _build_from_toc(
        self, 
        pages: List[Tuple[int, str]], 
        toc: List[Dict],
        max_pages_per_node: int
    ) -> TreeNode:
        """Build tree from extracted TOC"""
        root = TreeNode(
            node_id=self._generate_node_id(),
            title="Document",
            page_start=1,
            page_end=len(pages),
            level=0
        )
        
        # Convert pages to dict for easy lookup
        page_dict = {p: t for p, t in pages}
        
        # Build tree recursively
        current_level_1 = None
        current_level_2 = None
        
        for i, entry in enumerate(toc):
            title = entry['title']
            page = entry['page']
            level = entry['level']
            
            # Determine page range
            next_page = toc[i + 1]['page'] if i + 1 < len(toc) else len(pages) + 1
            page_end = min(next_page - 1, len(pages))
            
            # Extract content for this section
            content_pages = [page_dict.get(p, '') for p in range(page, page_end + 1)]
            content = '\n\n'.join(content_pages)
            
            # Create node
            node = TreeNode(
                node_id=self._generate_node_id(),
                title=title,
                page_start=page,
                page_end=page_end,
                level=level,
                content=content
            )
            
            # Add to tree based on level
            if level == 1:
                root.children.append(node)
                current_level_1 = node
                current_level_2 = None
            elif level == 2 and current_level_1:
                current_level_1.children.append(node)
                current_level_2 = node
            elif level == 3 and current_level_2:
                current_level_2.children.append(node)
        
        return root
    
    def _build_with_llm(
        self, 
        pages: List[Tuple[int, str]], 
        max_pages_per_node: int
    ) -> TreeNode:
        """
        Use LLM to infer document structure when no TOC exists.
        
        Strategy: 
        1. Sample pages throughout document
        2. Ask LLM to identify logical sections
        3. Build tree based on inferred structure
        """
        # Sample pages evenly throughout document
        num_pages = len(pages)
        sample_indices = list(range(0, num_pages, max(1, num_pages // 20)))[:20]
        
        sampled_text = "\n\n".join([
            f"=== PAGE {pages[i][0]} ===\n{pages[i][1][:500]}"
            for i in sample_indices
        ])
        
        prompt = f"""Analyze this document sample and identify its logical structure.

Document has {num_pages} total pages. Here are samples:

{sampled_text}

Infer the document structure and respond with JSON:
[
  {{"title": "Introduction", "page_start": 1, "page_end": 5, "level": 1}},
  {{"title": "Background", "page_start": 1, "page_end": 3, "level": 2}},
  ...
]

Rules:
- Infer logical section breaks based on content transitions
- level 1 = main sections, level 2 = subsections
- Ensure page ranges don't overlap
- Cover all {num_pages} pages

Respond ONLY with valid JSON array."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            structure = json.loads(response.choices[0].message.content)
            return self._build_from_structure(pages, structure)
        
        except Exception as e:
            print(f"⚠️ LLM structure inference failed: {e}")
            # Fallback: simple chunking
            return self._build_simple_chunks(pages, max_pages_per_node)
    
    def _build_from_structure(
        self, 
        pages: List[Tuple[int, str]], 
        structure: List[Dict]
    ) -> TreeNode:
        """Build tree from LLM-inferred structure"""
        root = TreeNode(
            node_id=self._generate_node_id(),
            title="Document",
            page_start=1,
            page_end=len(pages),
            level=0
        )
        
        page_dict = {p: t for p, t in pages}
        
        current_parent = root
        for entry in structure:
            title = entry['title']
            page_start = entry['page_start']
            page_end = entry['page_end']
            level = entry['level']
            
            # Extract content
            content_pages = [page_dict.get(p, '') for p in range(page_start, page_end + 1)]
            content = '\n\n'.join(content_pages)
            
            node = TreeNode(
                node_id=self._generate_node_id(),
                title=title,
                page_start=page_start,
                page_end=page_end,
                level=level,
                content=content
            )
            
            root.children.append(node)
        
        return root
    
    def _build_simple_chunks(
        self, 
        pages: List[Tuple[int, str]], 
        chunk_size: int
    ) -> TreeNode:
        """Fallback: simple page-based chunking"""
        root = TreeNode(
            node_id=self._generate_node_id(),
            title="Document",
            page_start=1,
            page_end=len(pages),
            level=0
        )
        
        for i in range(0, len(pages), chunk_size):
            chunk_pages = pages[i:i + chunk_size]
            page_start = chunk_pages[0][0]
            page_end = chunk_pages[-1][0]
            
            content = '\n\n'.join([t for _, t in chunk_pages])
            
            node = TreeNode(
                node_id=self._generate_node_id(),
                title=f"Section {i // chunk_size + 1}",
                page_start=page_start,
                page_end=page_end,
                level=1,
                content=content
            )
            
            root.children.append(node)
        
        return root
    
    def _add_summaries(self, node: TreeNode):
        """Recursively add LLM-generated summaries to each node"""
        if node.content and not node.summary:
            # Generate summary for this node
            prompt = f"""Summarize this document section in 2-3 sentences:

Title: {node.title}
Pages: {node.page_start}-{node.page_end}

Content:
{node.content[:3000]}

Provide a concise summary focusing on key topics and main points."""

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=150
                )
                
                node.summary = response.choices[0].message.content.strip()
            
            except Exception as e:
                print(f"⚠️ Summary generation failed for {node.node_id}: {e}")
        
        # Recursively process children
        for child in node.children:
            self._add_summaries(child)
    
    def _count_nodes(self, node: TreeNode) -> int:
        """Count total nodes in tree"""
        return 1 + sum(self._count_nodes(child) for child in node.children)


class LLMTreeSearcher:
    """
    Performs reasoning-based retrieval over document tree.
    
    Instead of embedding similarity, this uses the LLM to:
    1. Understand the query semantics
    2. Reason about which sections likely contain answers
    3. Return node IDs with traceable reasoning
    """
    
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
    
    def search(
        self, 
        query: str, 
        tree: TreeNode, 
        max_nodes: int = 5,
        domain_rules: Optional[str] = None
    ) -> List[str]:
        """
        Search tree for nodes relevant to query.
        
        Args:
            query: User's question
            tree: Document tree to search
            max_nodes: Maximum nodes to return
            domain_rules: Optional expert rules to guide search
            
        Returns:
            List of node IDs ranked by relevance
        """
        # Convert tree to searchable representation
        tree_repr = self._tree_to_search_repr(tree)
        
        # Build search prompt
        prompt = self._build_search_prompt(query, tree_repr, max_nodes, domain_rules)
        
        # Get LLM reasoning
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            result = json.loads(response.choices[0].message.content)
            node_ids = result.get('node_ids', [])
            reasoning = result.get('reasoning', '')
            
            print(f"\n🧠 LLM Reasoning:\n{reasoning}\n")
            print(f"📍 Retrieved nodes: {node_ids}\n")
            
            return node_ids[:max_nodes]
        
        except Exception as e:
            print(f"❌ Tree search failed: {e}")
            return []
    
    def _tree_to_search_repr(self, node: TreeNode, depth: int = 0) -> str:
        """Convert tree to text representation for LLM"""
        indent = "  " * depth
        repr_lines = [
            f"{indent}[{node.node_id}] {node.title} (pages {node.page_start}-{node.page_end})"
        ]
        
        if node.summary:
            repr_lines.append(f"{indent}  Summary: {node.summary}")
        
        for child in node.children:
            repr_lines.append(self._tree_to_search_repr(child, depth + 1))
        
        return "\n".join(repr_lines)
    
    def _build_search_prompt(
        self, 
        query: str, 
        tree_repr: str, 
        max_nodes: int,
        domain_rules: Optional[str]
    ) -> str:
        """Build prompt for tree search"""
        base_prompt = f"""You are a document search expert. Given a question and document tree structure, identify the most relevant sections.

QUESTION:
{query}

DOCUMENT STRUCTURE:
{tree_repr}

TASK:
1. Reason about which sections likely contain information to answer the question
2. Consider section titles, summaries, and hierarchical relationships
3. Return up to {max_nodes} most relevant node IDs

"""
        
        if domain_rules:
            base_prompt += f"""EXPERT RULES:
{domain_rules}

Follow these domain-specific guidelines when selecting sections.

"""
        
        base_prompt += """Respond ONLY with JSON in this format:
{
  "reasoning": "Your step-by-step reasoning about which sections are relevant",
  "node_ids": ["node_0001", "node_0002", ...]
}"""
        
        return base_prompt


class VectorlessRAG:
    """
    Main RAG system that combines all components.
    
    Pipeline:
    1. Build tree index from document
    2. Search tree for relevant nodes
    3. Retrieve node content
    4. Generate answer with citations
    """
    
    def __init__(self, openai_api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=openai_api_key)
        self.model = model
        self.pdf_processor = PDFProcessor()
        self.tree_builder = TreeBuilder(self.client, model)
        self.searcher = LLMTreeSearcher(self.client, model)
        self.tree = None
        self.tree_cache_path = None
    
    def index_document(
        self, 
        pdf_path: str, 
        cache_path: Optional[str] = None,
        max_pages_per_node: int = 10,
        generate_summaries: bool = True
    ) -> TreeNode:
        """
        Index a PDF document.
        
        Args:
            pdf_path: Path to PDF file
            cache_path: Optional path to save/load tree JSON
            max_pages_per_node: Max pages per tree node
            generate_summaries: Generate summaries for nodes
            
        Returns:
            Root node of document tree
        """
        # Check cache first
        if cache_path and os.path.exists(cache_path):
            print(f"📂 Loading cached tree from {cache_path}")
            with open(cache_path, 'r') as f:
                tree_data = json.load(f)
            self.tree = TreeNode.from_dict(tree_data)
            self.tree_cache_path = cache_path
            return self.tree
        
        # Extract pages
        pages = self.pdf_processor.extract_pages(pdf_path)
        
        # Build tree
        self.tree = self.tree_builder.build_tree_from_pages(
            pages, 
            max_pages_per_node, 
            generate_summaries
        )
        
        # Save to cache
        if cache_path:
            print(f"💾 Saving tree to {cache_path}")
            with open(cache_path, 'w') as f:
                json.dump(self.tree.to_dict(), f, indent=2)
            self.tree_cache_path = cache_path
        
        return self.tree
    
    def query(
        self, 
        question: str, 
        max_nodes: int = 5,
        domain_rules: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query the indexed document.
        
        Args:
            question: User's question
            max_nodes: Max sections to retrieve
            domain_rules: Optional expert guidance
            
        Returns:
            Dict with answer, sources, and metadata
        """
        if not self.tree:
            raise ValueError("No document indexed. Call index_document() first.")
        
        print(f"\n❓ Question: {question}\n")
        
        # Step 1: Search tree for relevant nodes
        node_ids = self.searcher.search(question, self.tree, max_nodes, domain_rules)
        
        if not node_ids:
            return {
                'answer': "No relevant sections found in the document.",
                'sources': [],
                'node_ids': []
            }
        
        # Step 2: Retrieve node content
        retrieved_nodes = self._retrieve_nodes(self.tree, node_ids)
        
        # Step 3: Generate answer
        answer = self._generate_answer(question, retrieved_nodes)
        
        # Step 4: Format sources
        sources = [
            {
                'node_id': node.node_id,
                'title': node.title,
                'pages': f"{node.page_start}-{node.page_end}",
                'summary': node.summary
            }
            for node in retrieved_nodes
        ]
        
        return {
            'answer': answer,
            'sources': sources,
            'node_ids': node_ids
        }
    
    def _retrieve_nodes(self, tree: TreeNode, node_ids: List[str]) -> List[TreeNode]:
        """Retrieve nodes by IDs from tree"""
        found_nodes = []
        
        def search_tree(node: TreeNode):
            if node.node_id in node_ids:
                found_nodes.append(node)
            for child in node.children:
                search_tree(child)
        
        search_tree(tree)
        
        # Sort by original order
        id_to_node = {n.node_id: n for n in found_nodes}
        return [id_to_node[nid] for nid in node_ids if nid in id_to_node]
    
    def _generate_answer(self, question: str, nodes: List[TreeNode]) -> str:
        """Generate answer from retrieved nodes"""
        context_parts = []
        for node in nodes:
            context_parts.append(f"""
Section: {node.title}
Pages: {node.page_start}-{node.page_end}
Content:
{node.content[:2000] if node.content else node.summary}
""")
        
        context = "\n\n---\n\n".join(context_parts)
        
        prompt = f"""Answer the question using ONLY the provided context. Cite specific sections in your answer.

CONTEXT:
{context}

QUESTION:
{question}

INSTRUCTIONS:
1. Answer clearly and concisely
2. Cite sections by title and page numbers
3. If the context doesn't contain enough information, say so
4. Use direct quotes when relevant

ANSWER:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            return f"Error generating answer: {e}"
    
    def print_tree(self, node: Optional[TreeNode] = None, depth: int = 0):
        """Print tree structure"""
        if node is None:
            node = self.tree
        
        if node is None:
            print("No tree indexed")
            return
        
        indent = "  " * depth
        print(f"{indent}├─ [{node.node_id}] {node.title} (pp. {node.page_start}-{node.page_end})")
        
        if node.summary and depth <= 2:  # Only show summaries for top levels
            print(f"{indent}   {node.summary[:100]}...")
        
        for child in node.children:
            self.print_tree(child, depth + 1)
