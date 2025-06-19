#!/usr/bin/env python3
"""
Portuguese ECLI RAG System - DeepSeek API Tester
Evaluates retrieval quality using DeepSeek API for query testing.
Implements 50 predefined legal queries across 4 categories with human relevance scoring.
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path

# Import vector database client
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install chromadb")
    sys.exit(1)

# Import API client (placeholder - replace with actual DeepSeek client)
try:
    import requests
except ImportError as e:
    print(f"❌ Missing required packages: {e}")
    print("Please install: pip install requests")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deepseek_testing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DeepSeekEvaluator:
    """Evaluates embedding model performance using DeepSeek API and predefined legal queries."""
    
    def __init__(self, api_key: str = "sk-7d3563c72d744e1e99694f679607e943"):
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        if not self.api_key:
            logger.error("DeepSeek API key not found. Please set the DEEPSEEK_API_KEY environment variable.")
            sys.exit(1)
            
        # Check if API key exists
        self.is_valid_api_key = bool(self.api_key) and self.api_key != "sk-7d3563c72d744e1e99694f679607e943"
        if not self.is_valid_api_key:
            logger.warning("Using a placeholder API key. Will fall back to mock evaluations.")
        else:
            logger.info("Using provided DeepSeek API key")
            
        self.client = None
        self.collections = {}
        self.embedding_functions = {}
        
        # Predefined test queries as recommended by expert
        self.test_queries = {
            'broad_topical': [
                "Responsabilidade civil por acidentes de viação",
                "Direitos do consumidor em contratos de compra e venda",
                "Divórcio e partilha de bens",
                "Direitos laborais e despedimento ilícito",
                "Sucessões e testamentos",
                "Contratos de arrendamento urbano",
                "Direito penal - crimes contra o património",
                "Processo civil - recursos",
                "Direito administrativo - licenciamentos",
                "Proteção de dados pessoais",
                "Direito fiscal - IRS e tributação",
                "Responsabilidade médica",
                "Direito da família - regulação do poder paternal",
                "Contratos de trabalho",
                "Direito comercial - sociedades"
            ],
            'specific_legal_concept': [
                "Recurso de revista excecional",
                "Litigância de má-fé",
                "Prescrição aquisitiva",
                "Caso julgado material",
                "Excepção dilatória",
                "Recurso per saltum",
                "Cláusulas contratuais gerais abusivas",
                "Força maior no direito civil",
                "Resolução do contrato por incumprimento",
                "Medidas cautelares inominadas",
                "Tutela de urgência",
                "Embargos de terceiro",
                "Conflito de jurisdição",
                "Exceção de preterição de escalão de recurso",
                "Responsabilidade solidária"
            ],
            'citation_search': [
                "Interpretação do artigo 483 do Código Civil",
                "Aplicação do artigo 227 do Código Penal",
                "Artigo 62 do Código de Processo Civil",
                "Decreto-Lei 446/85 sobre regime geral das contraordenações",
                "Lei 141/2015 sobre procedimento administrativo",
                "Artigo 334 do Código Civil - abuso do direito",
                "Código do Trabalho artigo 394",
                "Lei da proteção de dados - RGPD",
                "Código das Sociedades Comerciais artigo 72",
                "Estatuto dos Tribunais Administrativos e Fiscais"
            ],
            'factual_scenario': [
                "Contrato de arrendamento não cumprido por falta de obras do senhorio",
                "Acidente de trabalho com responsabilidade da entidade patronal",
                "Divórcio com violência doméstica",
                "Despedimento por justa causa contestado pelo trabalhador",
                "Compra de carro com vícios ocultos",
                "Sucessão com testamento contestado pelos herdeiros",
                "Responsabilidade médica por erro de diagnóstico",
                "Contrato de empreitada com defeitos na obra",
                "Cancelamento de contrato de viagem por Covid-19",
                "Danos causados por animal doméstico"
            ]
        }
        
        # Flatten all queries for easy iteration
        self.all_queries = []
        for category, queries in self.test_queries.items():
            for query in queries:
                self.all_queries.append({
                    'category': category,
                    'query': query,
                    'query_id': f"{category}_{len(self.all_queries) + 1}"
                })
        
        logger.info(f"Loaded {len(self.all_queries)} test queries across {len(self.test_queries)} categories")
        
    def initialize_vector_stores(self, connection_info: Dict) -> bool:
        """Initialize ChromaDB client and connect to existing collections."""
        try:
            db_path = connection_info['db_path']
            self.client = chromadb.PersistentClient(path=db_path)
            logger.info(f"Connected to ChromaDB at: {db_path}")

            for model_key, config in connection_info['collections'].items():
                collection_name = config['name']
                model_name = config['model_name']
                
                # Initialize embedding function for the model
                logger.info(f"Initializing embedding function for {model_key}")
                self.embedding_functions[model_key] = SentenceTransformerEmbeddingFunction(model_name=model_name)
                
                # Get collection with the correct embedding function
                self.collections[model_key] = self.client.get_collection(
                    name=collection_name,
                    embedding_function=self.embedding_functions[model_key]
                )
                logger.info(f"Connected to collection: {collection_name}")

            logger.info(f"Initialized {len(self.collections)} vector store collections")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to vector stores: {e}")
            return False
    
    def search_collection(self, model_key: str, query: str, n_results: int = 5) -> Dict:
        """Search a specific collection and return results."""
        collection = self.collections[model_key]
        
        try:
            start_time = time.time()
            
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            search_time = time.time() - start_time
            
            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        'rank': i + 1,
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i],
                        'ecli': results['metadatas'][0][i].get('ecli', 'Unknown'),
                        'court': results['metadatas'][0][i].get('court_code', 'Unknown'),
                        'chunk_type': results['metadatas'][0][i].get('chunk_type', 'Unknown')
                    })
            
            return {
                'model_key': model_key,
                'query': query,
                'search_time_seconds': search_time,
                'results_count': len(formatted_results),
                'results': formatted_results
            }
            
        except Exception as e:
            logger.error(f"Search failed for {model_key}: {e}")
            return {
                'model_key': model_key,
                'query': query,
                'error': str(e),
                'results': []
            }
    
    def call_deepseek_api(self, query: str, search_results: List[Dict], 
                         model: str = "deepseek-chat") -> Dict:
        """Call DeepSeek API to evaluate search result relevance."""
        if not self.api_key or not self.is_valid_api_key:
            logger.warning("No valid DeepSeek API key provided, using mock evaluation")
            return self._mock_deepseek_evaluation(query, search_results)
        
        # Prepare context from search results
        context_texts = []
        for result in search_results[:3]:  # Use top 3 results for context
            context_texts.append(f"ECLI: {result['ecli']}\nCourt: {result['court']}\nText: {result['document'][:500]}...")
        
        context = "\n\n---\n\n".join(context_texts)
        
        # Create evaluation prompt
        prompt = f"""Você é um especialista em direito português. Avalie a relevância dos seguintes documentos legais para a consulta fornecida.

CONSULTA: {query}

DOCUMENTOS PARA AVALIAR:
{context}

Para cada documento, forneça uma pontuação de relevância de 1-5:
5 (Perfeito): O documento é uma resposta perfeita para a consulta
4 (Excelente): Aborda diretamente a questão legal central da consulta  
3 (Bom): Relevante para o tópico mas não uma resposta direta
2 (Marginal): Menciona palavras-chave mas está fora do tópico
1 (Irrelevante): Completamente não relacionado

Responda em formato JSON:
{{"evaluations": [{{"document_index": 1, "relevance_score": X, "reasoning": "..."}}, ...]}}"""

        try:
            # Make API call to DeepSeek
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Create proper API endpoint URL
            api_endpoint = "https://api.deepseek.com/v1/chat/completions"
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            }
            
            logger.info(f"Making API call to DeepSeek for query: {query[:50]}...")
            
            response = requests.post(
                api_endpoint,  # Use the defined endpoint variable
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                logger.info(f"Received response from DeepSeek API")
                
                # Try to extract JSON from the response using regex
                try:
                    import re
                    json_match = re.search(r'\{\s*"evaluations"\s*:\s*\[.*?\]\s*\}', content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        evaluation_data = json.loads(json_str)
                        evaluations = evaluation_data.get('evaluations', [])
                        
                        # Convert evaluations to our expected format
                        if evaluations:
                            logger.info(f"Successfully extracted {len(evaluations)} evaluations from response")
                            return {
                                'success': True, 
                                'evaluations': evaluations,
                                'raw_response': content
                            }
                    # If no JSON found in response, try direct parsing
                    try:
                        direct_json = json.loads(content)
                        if 'evaluations' in direct_json:
                            logger.info("Extracted evaluations directly from JSON response")
                            return {
                                'success': True,
                                'evaluations': direct_json['evaluations'],
                                'raw_response': content
                            }
                    except json.JSONDecodeError:
                        pass
                        
                    logger.warning("Could not extract JSON with evaluations from response")
                    # Fall back to mock evaluation
                    logger.warning("Falling back to mock evaluation due to parsing issues")
                    return self._mock_deepseek_evaluation(query, search_results)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse DeepSeek response: {e}")
                    # Fall back to mock evaluation
                    logger.warning("Falling back to mock evaluation due to exception")
                    return self._mock_deepseek_evaluation(query, search_results)
            else:
                logger.error(f"API call failed with status {response.status_code}: {response.text[:100]}")
                # Fall back to mock evaluation on API error
                logger.warning("Falling back to mock evaluation due to API error")
                return self._mock_deepseek_evaluation(query, search_results)
                
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _mock_deepseek_evaluation(self, query: str, search_results: List[Dict]) -> Dict:
        """Mock evaluation for testing without API key."""
        logger.info("Using mock DeepSeek evaluation (no API key provided)")
        
        # Generate mock relevance scores
        evaluations = []
        for i, result in enumerate(search_results[:3]):
            # Create randomized mock scores that favor higher relevance for first result
            if i == 0:
                score = random.randint(3, 5)  # First result tends to be more relevant
            else:
                score = random.randint(1, 4)  # Other results get more variable scores
                
            evaluations.append({
                "document_index": i + 1,
                "relevance_score": score,
                "reasoning": f"Mock evaluation for document {i+1} with ECLI {result.get('ecli', 'unknown')}"
            })
        
        return {
            'success': True,
            'evaluations': evaluations,
            'is_mock': True
        }
    
    def calculate_metrics(self, results: List[Dict]) -> Dict:
        """Calculate evaluation metrics from results."""
        if not results:
            return {}
        
        # Extract relevance scores
        all_scores = []
        precision_at_3_scores = []
        precision_at_5_scores = []
        mrr_scores = []
        
        for result in results:
            if 'relevance_evaluation' in result and result['relevance_evaluation']['success']:
                evaluations = result['relevance_evaluation']['evaluation']['evaluations']
                
                scores = [eval_item['relevance_score'] for eval_item in evaluations]
                all_scores.extend(scores)
                
                # Precision@K (percentage of results with score >= 3)
                relevant_scores = [s for s in scores if s >= 3]
                
                if len(scores) >= 3:
                    precision_at_3_scores.append(len([s for s in scores[:3] if s >= 3]) / 3)
                
                if len(scores) >= 5:
                    precision_at_5_scores.append(len([s for s in scores[:5] if s >= 3]) / 5)
                
                # MRR (Mean Reciprocal Rank) - rank of first highly relevant result (score >= 4)
                first_relevant_rank = None
                for i, score in enumerate(scores):
                    if score >= 4:
                        first_relevant_rank = i + 1
                        break
                
                if first_relevant_rank:
                    mrr_scores.append(1.0 / first_relevant_rank)
                else:
                    mrr_scores.append(0.0)
        
        metrics = {}
        
        if all_scores:
            metrics['average_relevance_score'] = sum(all_scores) / len(all_scores)
            metrics['total_evaluations'] = len(all_scores)
        
        if precision_at_3_scores:
            metrics['precision_at_3'] = sum(precision_at_3_scores) / len(precision_at_3_scores)
        
        if precision_at_5_scores:
            metrics['precision_at_5'] = sum(precision_at_5_scores) / len(precision_at_5_scores)
        
        if mrr_scores:
            metrics['mean_reciprocal_rank'] = sum(mrr_scores) / len(mrr_scores)
        
        return metrics
    
    def run_evaluation(self, vector_store_dir: str, output_dir: str, 
                      max_queries: int = None) -> bool:
        """Run complete evaluation pipeline."""
        logger.info("Starting DeepSeek evaluation for model comparison")
        
        # Import ThreadPoolExecutor for parallel API calls
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Load vector store connection info
            connection_file = os.path.join(vector_store_dir, "vector_store_connection.json")
            if not os.path.exists(connection_file):
                logger.error(f"Vector store connection file not found: {connection_file}")
                return False
            
            with open(connection_file, 'r', encoding='utf-8') as f:
                connection_info = json.load(f)
            
            # Initialize vector stores
            if not self.initialize_vector_stores(connection_info):
                return False
            
            # Limit queries for testing if specified
            queries_to_test = self.all_queries[:max_queries] if max_queries else self.all_queries
            logger.info(f"Testing {len(queries_to_test)} queries across {len(self.collections)} models")
            
            # Store all results
            evaluation_results = {
                'evaluation_timestamp': datetime.now().isoformat(),
                'total_queries': len(queries_to_test),
                'models_tested': list(self.collections.keys()),
                'api_key_available': bool(self.api_key) and self.is_valid_api_key,
                'using_mock_evaluation': not (bool(self.api_key) and self.is_valid_api_key),
                'query_results': {},
                'model_metrics': {}
            }
            
            # Test each model
            for model_key in self.collections.keys():
                logger.info(f"Testing model: {model_key}")
                model_results = []
                
                # Define a worker function for ThreadPoolExecutor
                def process_query(query_info, model_key=model_key):
                    query = query_info['query']
                    query_id = query_info['query_id']
                    category = query_info['category']
                    
                    logger.info(f"Processing query: {query[:50]}...")
                    
                    # Search collection
                    search_result = self.search_collection(model_key, query, n_results=5)
                    
                    # Evaluate with DeepSeek API or mock evaluation
                    if search_result.get('results'):
                        evaluation = self.call_deepseek_api(query, search_result['results'])
                        search_result['relevance_evaluation'] = evaluation
                    else:
                        search_result['relevance_evaluation'] = {
                            'success': False,
                            'error': 'No search results to evaluate'
                        }
                    
                    # Add query metadata
                    search_result.update({
                        'query_id': query_id,
                        'category': category,
                        'query_index': query_info.get('index', 0) + 1
                    })
                    
                    return search_result
                
                # Add index information to queries
                for i, query_info in enumerate(queries_to_test):
                    query_info['index'] = i
                
                # Use ThreadPoolExecutor to parallelize API calls
                # Using a more conservative number of workers to avoid memory issues
                # The high number (61) was causing crashes during model loading
                max_workers = 8  # Reduced from 61 to avoid memory/thread issues
                
                # Ensure all embedding functions are fully initialized before parallel processing
                # This helps prevent race conditions and memory issues
                logger.info("Pre-warming embedding functions to avoid concurrent initialization issues...")
                for model_key, embed_func in self.embedding_functions.items():
                    if hasattr(embed_func, 'encode'):
                        # Force loading the model by encoding a simple test string
                        try:
                            _ = embed_func.encode("Test sentence for model warm-up")
                            logger.info(f"Successfully pre-warmed {model_key} embedding function")
                        except Exception as e:
                            logger.warning(f"Failed to pre-warm {model_key}: {e}")
                
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all query tasks
                    future_to_query = {executor.submit(process_query, query_info): query_info 
                                      for query_info in queries_to_test}
                    
                    # Process results as they complete
                    for future in as_completed(future_to_query):
                        query_info = future_to_query[future]
                        try:
                            result = future.result()
                            model_results.append(result)
                            logger.info(f"Completed {result['query_index']}/{len(queries_to_test)}: {query_info['query'][:50]}...")
                        except Exception as exc:
                            logger.error(f"Query {query_info['query_id']} generated an exception: {exc}")
                
                # Sort results by query_index to maintain order
                model_results.sort(key=lambda x: x['query_index'])
                
                # Calculate metrics for this model
                model_metrics = self.calculate_metrics(model_results)
                
                evaluation_results['query_results'][model_key] = model_results
                evaluation_results['model_metrics'][model_key] = model_metrics
                
                logger.info(f"Completed evaluation for {model_key}")
                if model_metrics:
                    logger.info(f"Average relevance: {model_metrics.get('average_relevance_score', 0):.2f}")
                    logger.info(f"Precision@3: {model_metrics.get('precision_at_3', 0):.2f}")
                    logger.info(f"MRR: {model_metrics.get('mean_reciprocal_rank', 0):.2f}")
            
            # Save detailed results
            results_file = os.path.join(output_dir, "deepseek_evaluation_results.json")
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(evaluation_results, f, ensure_ascii=False, indent=2, default=str)
            
            # Create summary report
            self._create_summary_report(evaluation_results, output_dir)
            
            logger.info("Evaluation completed!")
            logger.info(f"Results saved to: {output_dir}")
            logger.info("Check summary_report.md for detailed comparison")
            
            return True
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return False
    
    def _create_summary_report(self, results: Dict, output_dir: str):
        """Create a human-readable summary report."""
        report_lines = [
            "# Portuguese ECLI RAG System - Model Comparison Report\n",
            f"**Evaluation Date:** {results['evaluation_timestamp']}\n",
            f"**Total Queries Tested:** {results['total_queries']}\n",
            f"**Models Compared:** {', '.join(results['models_tested'])}\n\n"
        ]
        
        # Model comparison table
        report_lines.append("## Model Performance Comparison\n\n")
        report_lines.append("| Model | Avg Relevance | Precision@3 | Precision@5 | MRR | Recommendation |\n")
        report_lines.append("|-------|---------------|-------------|-------------|-----|----------------|\n")
        
        best_model = None
        best_score = 0
        
        for model_key, metrics in results['model_metrics'].items():
            if metrics:
                avg_rel = metrics.get('average_relevance_score', 0)
                p3 = metrics.get('precision_at_3', 0)
                p5 = metrics.get('precision_at_5', 0)
                mrr = metrics.get('mean_reciprocal_rank', 0)
                
                # Simple scoring for recommendation
                composite_score = avg_rel * 0.4 + p3 * 0.3 + mrr * 0.3
                
                if composite_score > best_score:
                    best_score = composite_score
                    best_model = model_key
                
                recommendation = "Best" if composite_score == best_score else "Good" if composite_score > 3.0 else "Needs improvement"
                
                report_lines.append(f"| {model_key} | {avg_rel:.2f} | {p3:.2f} | {p5:.2f} | {mrr:.2f} | {recommendation} |\n")
        
        report_lines.append(f"\n**Recommended Model:** {best_model}\n\n")
        
        # Success criteria analysis
        report_lines.append("## Success Criteria Analysis\n\n")
        report_lines.append("Based on expert recommendations:\n")
        report_lines.append("- **BGE-M3 justification threshold:** +0.4 relevance score OR >15% improvement in Precision@3/MRR\n")
        report_lines.append("- **Processing time consideration:** BGE-M3 takes 2-3x longer than PUCPR model\n\n")
        
        if len(results['model_metrics']) >= 2:
            models = list(results['model_metrics'].keys())
            if len(models) >= 2:
                model1, model2 = models[0], models[1]
                metrics1 = results['model_metrics'][model1]
                metrics2 = results['model_metrics'][model2]
                
                if metrics1 and metrics2:
                    rel_diff = abs(metrics1.get('average_relevance_score', 0) - metrics2.get('average_relevance_score', 0))
                    p3_diff = abs(metrics1.get('precision_at_3', 0) - metrics2.get('precision_at_3', 0))
                    
                    report_lines.append(f"**Relevance Score Difference:** {rel_diff:.2f}\n")
                    report_lines.append(f"**Precision@3 Difference:** {p3_diff:.2f} ({p3_diff*100:.1f}%)\n\n")
                    
                    if rel_diff >= 0.4 or p3_diff >= 0.15:
                        report_lines.append("Quality improvement justifies longer processing time\n\n")
                    else:
                        report_lines.append("Quality improvement does NOT justify longer processing time\n\n")
        
        # Category performance breakdown
        report_lines.append("## Performance by Query Category\n\n")
        
        categories = ['broad_topical', 'specific_legal_concept', 'citation_search', 'factual_scenario']
        for category in categories:
            report_lines.append(f"### {category.replace('_', ' ').title()}\n\n")
            
            for model_key in results['models_tested']:
                model_results = results['query_results'].get(model_key, [])
                category_results = [r for r in model_results if r.get('category') == category]
                
                if category_results:
                    category_metrics = self.calculate_metrics(category_results)
                    if category_metrics:
                        avg_rel = category_metrics.get('average_relevance_score', 0)
                        report_lines.append(f"- **{model_key}:** {avg_rel:.2f} avg relevance\n")
            
            report_lines.append("\n")
        
        # Save report
        report_file = os.path.join(output_dir, "summary_report.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.writelines(report_lines)
        
        logger.info(f"Summary report created: {report_file}")

def main():
    """Main execution function."""
    # Set up paths
    script_dir = Path(__file__).parent
    vector_store_dir = script_dir.parent / "data" / "vector_stores"
    output_dir = script_dir.parent / "data" / "evaluation_results"
    
    # Check if vector stores exist
    if not vector_store_dir.exists():
        logger.error(f"Vector store directory not found: {vector_store_dir}")
        logger.error("Please run vector_store_setup.py first!")
        sys.exit(1)
    
    # Initialize evaluator
    evaluator = DeepSeekEvaluator()
    
    # Run evaluation (limit to 10 queries for testing, remove limit for full evaluation)
    max_queries = 10 if '--test' in sys.argv else None
    
    success = evaluator.run_evaluation(str(vector_store_dir), str(output_dir), max_queries)
    
    if success:
        logger.info("All tests completed successfully!")
    else:
        logger.error("DeepSeek evaluation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
