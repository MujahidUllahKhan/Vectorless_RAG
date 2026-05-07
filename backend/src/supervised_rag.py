"""
Supervised RAG Component
========================
This module implements supervised learning for RAG quality improvement.

Key Concepts:
- Supervised QA Pairs: Ground truth question-answer pairs
- Retrieval Evaluation: Metrics for retrieval quality
- Answer Quality Metrics: ROUGE, BLEU, semantic similarity
- Feedback Loop: Use supervised data to improve retrieval rules
"""

import json
import os
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import numpy as np
from openai import OpenAI


@dataclass
class SupervisedQAPair:
    """
    Supervised question-answer pair with metadata.
    
    Attributes:
        question: The query text
        ground_truth_answer: Expected/correct answer
        relevant_node_ids: Node IDs that should be retrieved
        context_needed: What context sections are needed
        difficulty: easy/medium/hard
        category: Topic category (optional)
    """
    question: str
    ground_truth_answer: str
    relevant_node_ids: List[str]
    context_needed: str
    difficulty: str = "medium"
    category: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SupervisedQAPair':
        return cls(**data)


@dataclass
class RetrievalMetrics:
    """
    Metrics for evaluating retrieval quality.
    
    Metrics:
        precision: Fraction of retrieved nodes that are relevant
        recall: Fraction of relevant nodes that were retrieved
        f1_score: Harmonic mean of precision and recall
        mrr: Mean Reciprocal Rank (rank of first relevant result)
        ndcg: Normalized Discounted Cumulative Gain
    """
    precision: float
    recall: float
    f1_score: float
    mrr: float
    ndcg: float
    
    def __str__(self) -> str:
        return f"""
Retrieval Metrics:
  Precision: {self.precision:.3f}
  Recall:    {self.recall:.3f}
  F1 Score:  {self.f1_score:.3f}
  MRR:       {self.mrr:.3f}
  NDCG:      {self.ndcg:.3f}
"""


@dataclass
class AnswerMetrics:
    """
    Metrics for evaluating answer quality.
    
    Metrics:
        exact_match: 1 if answer exactly matches ground truth, else 0
        rouge_1: ROUGE-1 F1 score (unigram overlap)
        rouge_l: ROUGE-L F1 score (longest common subsequence)
        semantic_similarity: Cosine similarity of embeddings (0-1)
    """
    exact_match: float
    rouge_1: float
    rouge_l: float
    semantic_similarity: float
    
    def __str__(self) -> str:
        return f"""
Answer Quality Metrics:
  Exact Match:        {self.exact_match:.3f}
  ROUGE-1:            {self.rouge_1:.3f}
  ROUGE-L:            {self.rouge_l:.3f}
  Semantic Similarity: {self.semantic_similarity:.3f}
"""


class SupervisedRAGEvaluator:
    """
    Evaluates RAG system performance on supervised dataset.
    
    This class:
    1. Loads supervised QA pairs
    2. Runs RAG on each question
    3. Computes retrieval and answer metrics
    4. Identifies failure patterns
    5. Suggests improvements
    """
    
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
        self.qa_pairs: List[SupervisedQAPair] = []
    
    def load_qa_pairs(self, json_path: str):
        """Load supervised QA pairs from JSON file"""
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        self.qa_pairs = [SupervisedQAPair.from_dict(item) for item in data]
        print(f"✅ Loaded {len(self.qa_pairs)} supervised QA pairs")
    
    def add_qa_pair(
        self,
        question: str,
        ground_truth_answer: str,
        relevant_node_ids: List[str],
        context_needed: str,
        difficulty: str = "medium",
        category: Optional[str] = None
    ):
        """Add a single QA pair"""
        qa = SupervisedQAPair(
            question=question,
            ground_truth_answer=ground_truth_answer,
            relevant_node_ids=relevant_node_ids,
            context_needed=context_needed,
            difficulty=difficulty,
            category=category
        )
        self.qa_pairs.append(qa)
    
    def save_qa_pairs(self, json_path: str):
        """Save QA pairs to JSON"""
        data = [qa.to_dict() for qa in self.qa_pairs]
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"💾 Saved {len(self.qa_pairs)} QA pairs to {json_path}")
    
    def evaluate_retrieval(
        self,
        retrieved_node_ids: List[str],
        relevant_node_ids: List[str]
    ) -> RetrievalMetrics:
        """
        Compute retrieval metrics.
        
        Args:
            retrieved_node_ids: Nodes returned by RAG system
            relevant_node_ids: Ground truth relevant nodes
            
        Returns:
            RetrievalMetrics object
        """
        retrieved_set = set(retrieved_node_ids)
        relevant_set = set(relevant_node_ids)
        
        # Precision: fraction of retrieved that are relevant
        if len(retrieved_set) == 0:
            precision = 0.0
        else:
            precision = len(retrieved_set & relevant_set) / len(retrieved_set)
        
        # Recall: fraction of relevant that were retrieved
        if len(relevant_set) == 0:
            recall = 1.0  # Edge case
        else:
            recall = len(retrieved_set & relevant_set) / len(relevant_set)
        
        # F1 score
        if precision + recall == 0:
            f1_score = 0.0
        else:
            f1_score = 2 * (precision * recall) / (precision + recall)
        
        # Mean Reciprocal Rank (MRR)
        mrr = 0.0
        for i, node_id in enumerate(retrieved_node_ids):
            if node_id in relevant_set:
                mrr = 1.0 / (i + 1)
                break
        
        # NDCG (simplified version)
        dcg = 0.0
        idcg = 0.0
        
        for i, node_id in enumerate(retrieved_node_ids):
            if node_id in relevant_set:
                dcg += 1.0 / np.log2(i + 2)  # +2 because positions start at 0
        
        for i in range(min(len(relevant_set), len(retrieved_node_ids))):
            idcg += 1.0 / np.log2(i + 2)
        
        ndcg = dcg / idcg if idcg > 0 else 0.0
        
        return RetrievalMetrics(
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            mrr=mrr,
            ndcg=ndcg
        )
    
    def evaluate_answer(
        self,
        generated_answer: str,
        ground_truth_answer: str
    ) -> AnswerMetrics:
        """
        Compute answer quality metrics.
        
        Args:
            generated_answer: Answer from RAG system
            ground_truth_answer: Ground truth answer
            
        Returns:
            AnswerMetrics object
        """
        # Exact match (case-insensitive, normalized)
        gen_norm = ' '.join(generated_answer.lower().split())
        gt_norm = ' '.join(ground_truth_answer.lower().split())
        exact_match = 1.0 if gen_norm == gt_norm else 0.0
        
        # ROUGE scores (simplified implementation)
        rouge_1 = self._compute_rouge_1(generated_answer, ground_truth_answer)
        rouge_l = self._compute_rouge_l(generated_answer, ground_truth_answer)
        
        # Semantic similarity using embeddings
        semantic_sim = self._compute_semantic_similarity(
            generated_answer, 
            ground_truth_answer
        )
        
        return AnswerMetrics(
            exact_match=exact_match,
            rouge_1=rouge_1,
            rouge_l=rouge_l,
            semantic_similarity=semantic_sim
        )
    
    def _compute_rouge_1(self, generated: str, reference: str) -> float:
        """
        ROUGE-1: Unigram overlap F1 score
        
        Measures word-level overlap between generated and reference
        """
        gen_words = set(generated.lower().split())
        ref_words = set(reference.lower().split())
        
        if len(gen_words) == 0 or len(ref_words) == 0:
            return 0.0
        
        overlap = len(gen_words & ref_words)
        
        precision = overlap / len(gen_words)
        recall = overlap / len(ref_words)
        
        if precision + recall == 0:
            return 0.0
        
        f1 = 2 * (precision * recall) / (precision + recall)
        return f1
    
    def _compute_rouge_l(self, generated: str, reference: str) -> float:
        """
        ROUGE-L: Longest Common Subsequence (LCS) based F1
        
        Measures longest common word sequence
        """
        gen_words = generated.lower().split()
        ref_words = reference.lower().split()
        
        # Compute LCS length
        lcs_length = self._lcs_length(gen_words, ref_words)
        
        if len(gen_words) == 0 or len(ref_words) == 0:
            return 0.0
        
        precision = lcs_length / len(gen_words)
        recall = lcs_length / len(ref_words)
        
        if precision + recall == 0:
            return 0.0
        
        f1 = 2 * (precision * recall) / (precision + recall)
        return f1
    
    def _lcs_length(self, seq1: List[str], seq2: List[str]) -> int:
        """Compute Longest Common Subsequence length"""
        m, n = len(seq1), len(seq2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i-1] == seq2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        return dp[m][n]
    
    def _compute_semantic_similarity(
        self, 
        text1: str, 
        text2: str
    ) -> float:
        """
        Compute semantic similarity using OpenAI embeddings.
        
        Returns cosine similarity (0-1)
        """
        try:
            # Get embeddings
            response1 = self.client.embeddings.create(
                input=text1,
                model="text-embedding-3-small"
            )
            emb1 = np.array(response1.data[0].embedding)
            
            response2 = self.client.embeddings.create(
                input=text2,
                model="text-embedding-3-small"
            )
            emb2 = np.array(response2.data[0].embedding)
            
            # Cosine similarity
            similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
            return float(similarity)
        
        except Exception as e:
            print(f"⚠️ Embedding similarity failed: {e}")
            return 0.0
    
    def evaluate_rag_system(
        self,
        rag_system,  # VectorlessRAG instance
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Evaluate RAG system on all supervised QA pairs.
        
        Args:
            rag_system: VectorlessRAG instance
            verbose: Print individual results
            
        Returns:
            Dict with aggregate metrics and per-question results
        """
        if not self.qa_pairs:
            raise ValueError("No QA pairs loaded. Call load_qa_pairs() first.")
        
        results = []
        
        retrieval_metrics_list = []
        answer_metrics_list = []
        
        print("\n" + "="*80)
        print("📊 EVALUATING RAG SYSTEM ON SUPERVISED DATASET")
        print("="*80 + "\n")
        
        for i, qa in enumerate(self.qa_pairs, 1):
            if verbose:
                print(f"\n--- Question {i}/{len(self.qa_pairs)} ---")
                print(f"Q: {qa.question}")
                print(f"Difficulty: {qa.difficulty}")
                if qa.category:
                    print(f"Category: {qa.category}")
            
            # Run RAG query
            try:
                rag_result = rag_system.query(qa.question, max_nodes=5)
                
                retrieved_ids = rag_result['node_ids']
                generated_answer = rag_result['answer']
                
                # Evaluate retrieval
                ret_metrics = self.evaluate_retrieval(
                    retrieved_ids,
                    qa.relevant_node_ids
                )
                
                # Evaluate answer
                ans_metrics = self.evaluate_answer(
                    generated_answer,
                    qa.ground_truth_answer
                )
                
                retrieval_metrics_list.append(ret_metrics)
                answer_metrics_list.append(ans_metrics)
                
                if verbose:
                    print(f"\n✅ Retrieved nodes: {retrieved_ids}")
                    print(f"✅ Expected nodes: {qa.relevant_node_ids}")
                    print(ret_metrics)
                    print(ans_metrics)
                    print(f"\nGenerated Answer:\n{generated_answer}")
                    print(f"\nGround Truth:\n{qa.ground_truth_answer}")
                
                results.append({
                    'question': qa.question,
                    'difficulty': qa.difficulty,
                    'category': qa.category,
                    'retrieved_nodes': retrieved_ids,
                    'expected_nodes': qa.relevant_node_ids,
                    'generated_answer': generated_answer,
                    'ground_truth': qa.ground_truth_answer,
                    'retrieval_metrics': asdict(ret_metrics),
                    'answer_metrics': asdict(ans_metrics)
                })
            
            except Exception as e:
                print(f"❌ Error processing question {i}: {e}")
                results.append({
                    'question': qa.question,
                    'error': str(e)
                })
        
        # Compute aggregate metrics
        print("\n" + "="*80)
        print("📈 AGGREGATE METRICS")
        print("="*80 + "\n")
        
        aggregate = self._compute_aggregate_metrics(
            retrieval_metrics_list,
            answer_metrics_list
        )
        
        print(aggregate['summary'])
        
        return {
            'aggregate_metrics': aggregate,
            'per_question_results': results
        }
    
    def _compute_aggregate_metrics(
        self,
        retrieval_metrics: List[RetrievalMetrics],
        answer_metrics: List[AnswerMetrics]
    ) -> Dict[str, Any]:
        """Compute mean and std of all metrics"""
        
        if not retrieval_metrics or not answer_metrics:
            return {
                'summary': "No results to aggregate",
                'retrieval': {},
                'answer': {}
            }
        
        # Retrieval aggregates
        ret_data = {
            'precision': [m.precision for m in retrieval_metrics],
            'recall': [m.recall for m in retrieval_metrics],
            'f1_score': [m.f1_score for m in retrieval_metrics],
            'mrr': [m.mrr for m in retrieval_metrics],
            'ndcg': [m.ndcg for m in retrieval_metrics]
        }
        
        ret_agg = {
            metric: {
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values)
            }
            for metric, values in ret_data.items()
        }
        
        # Answer aggregates
        ans_data = {
            'exact_match': [m.exact_match for m in answer_metrics],
            'rouge_1': [m.rouge_1 for m in answer_metrics],
            'rouge_l': [m.rouge_l for m in answer_metrics],
            'semantic_similarity': [m.semantic_similarity for m in answer_metrics]
        }
        
        ans_agg = {
            metric: {
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values)
            }
            for metric, values in ans_data.items()
        }
        
        # Format summary
        summary = f"""
RETRIEVAL PERFORMANCE:
  Precision:  {ret_agg['precision']['mean']:.3f} ± {ret_agg['precision']['std']:.3f}
  Recall:     {ret_agg['recall']['mean']:.3f} ± {ret_agg['recall']['std']:.3f}
  F1 Score:   {ret_agg['f1_score']['mean']:.3f} ± {ret_agg['f1_score']['std']:.3f}
  MRR:        {ret_agg['mrr']['mean']:.3f} ± {ret_agg['mrr']['std']:.3f}
  NDCG:       {ret_agg['ndcg']['mean']:.3f} ± {ret_agg['ndcg']['std']:.3f}

ANSWER QUALITY:
  Exact Match:        {ans_agg['exact_match']['mean']:.3f} ± {ans_agg['exact_match']['std']:.3f}
  ROUGE-1:            {ans_agg['rouge_1']['mean']:.3f} ± {ans_agg['rouge_1']['std']:.3f}
  ROUGE-L:            {ans_agg['rouge_l']['mean']:.3f} ± {ans_agg['rouge_l']['std']:.3f}
  Semantic Similarity: {ans_agg['semantic_similarity']['mean']:.3f} ± {ans_agg['semantic_similarity']['std']:.3f}
"""
        
        return {
            'summary': summary,
            'retrieval': ret_agg,
            'answer': ans_agg
        }


class DomainRuleLearner:
    """
    Learns domain-specific retrieval rules from supervised data.
    
    This component analyzes failure patterns and suggests improvements:
    1. Which node types are frequently missed?
    2. What query patterns need special handling?
    3. What domain rules would improve retrieval?
    """
    
    def __init__(self, openai_client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
    
    def analyze_failures(
        self,
        evaluation_results: Dict[str, Any]
    ) -> str:
        """
        Analyze evaluation results to identify failure patterns.
        
        Args:
            evaluation_results: Output from SupervisedRAGEvaluator
            
        Returns:
            Analysis text with suggested improvements
        """
        per_question = evaluation_results.get('per_question_results', [])
        
        # Find low-performing questions
        failures = []
        for result in per_question:
            if 'retrieval_metrics' not in result:
                continue
            
            f1 = result['retrieval_metrics'].get('f1_score', 0)
            
            if f1 < 0.5:  # Threshold for "failure"
                failures.append({
                    'question': result['question'],
                    'retrieved': result.get('retrieved_nodes', []),
                    'expected': result.get('expected_nodes', []),
                    'f1': f1
                })
        
        if not failures:
            return "✅ No significant retrieval failures detected!"
        
        # Use LLM to analyze patterns
        failure_summary = json.dumps(failures, indent=2)
        
        prompt = f"""Analyze these RAG retrieval failures and suggest improvements.

FAILURES:
{failure_summary}

For each failure, the system retrieved wrong nodes. Analyze:
1. What patterns do you see in the failures?
2. What types of questions are problematic?
3. What domain-specific rules could help?

Provide concrete, actionable suggestions for improving retrieval.
Format as a numbered list of specific rules to add."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            
            analysis = response.choices[0].message.content
            
            return f"""
📊 FAILURE ANALYSIS
{'='*60}
Total failures (F1 < 0.5): {len(failures)}

{analysis}
"""
        
        except Exception as e:
            return f"❌ Analysis failed: {e}"
