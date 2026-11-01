import os
from typing import List, Dict, Any, Tuple
from .embeddings import EmbeddingsGenerator
from .faiss_index import FaissIndexManager
import logging

logger = logging.getLogger(__name__)

class SearchManager:
    def __init__(self):
        self.embeddings_generator = EmbeddingsGenerator()
        self.index_manager = FaissIndexManager()
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def index_file(self, file_path: str, content: str) -> bool:
        """Index a single file"""
        try:
            # Generate embedding for the file content
            embedding = self.embeddings_generator.generate_embedding(content)
            if embedding is None:
                logger.error(f"Failed to generate embedding for {file_path}")
                return False
            
            # Add to FAISS index
            self.index_manager.add_vectors([embedding], [file_path])
            logger.info(f"Successfully indexed {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error indexing {file_path}: {str(e)}")
            return False
    
    def index_files(self, files: List[Dict[str, str]]) -> Dict[str, bool]:
        """Index multiple files"""
        results = {}
        for file_info in files:
            file_path = file_info['path']
            content = file_info['content']
            success = self.index_file(file_path, content)
            results[file_path] = success
        return results
    
    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for files using a text query"""
        try:
            # Generate embedding for the query
            query_embedding = self.embeddings_generator.generate_embedding(query)
            if query_embedding is None:
                logger.error("Failed to generate query embedding")
                return []
            
            # Search the index
            results = self.index_manager.search(query_embedding, k)
            
            # Format results
            formatted_results = []
            for file_path, distance in results:
                formatted_results.append({
                    'file_path': file_path,
                    'relevance_score': 1.0 / (1.0 + distance),  # Convert distance to similarity score
                    'distance': distance
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            return []
    
    def remove_file(self, file_path: str) -> bool:
        """Remove a file from the index"""
        try:
            self.index_manager.remove_file(file_path)
            logger.info(f"Successfully removed {file_path} from index")
            return True
        except Exception as e:
            logger.error(f"Error removing {file_path} from index: {str(e)}")
            return False
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the search index"""
        return {
            'total_files': self.index_manager.get_total_files(),
            'index_path': self.index_manager.index_path
        } 