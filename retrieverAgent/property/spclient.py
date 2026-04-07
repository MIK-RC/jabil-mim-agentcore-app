import boto3
import json
import logging
from typing import List, Dict, Optional
from strands import tool
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import os
logger = logging.getLogger(__name__)

class SharePointClient:
    def __init__(self, region='us-east-1', host=None):
        """
        Initialize SharePoint/OpenSearch client with AOSS connection
        
        Args:
            region: AWS region for AOSS
            host: OpenSearch endpoint URL
        """
        # Setup OpenSearch client
        self.host = os.environ.get("OPENSEARCH_HOST", host)
        service = 'aoss'
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, service)
        print(f"Credentials obtained for OpenSearch client: {credentials.access_key} / {credentials.account_id} / {credentials.secret_key}")
        
        self.region = region
        self.auth = auth
        
        if self.host:
            self.client = OpenSearch(
                hosts=[{'host': self.host, 'port': 443}],
                http_auth=self.auth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
            )
            print(f"Initialized OpenSearch client with host: {self.host}")
        else:
            print("No OpenSearch host provided. Client not initialized.")
    
    def get_embedding(self, text_chunk: str) -> List[float]:
        """
        Generate embeddings via Amazon Bedrock using Cohere Embed v4.
        
        Args:
            text_chunk: Text to embed
        
        Returns:
            List[float]: Embedding vector (1024 dimensions for Cohere v4)
        """
        try:
            bedrock = boto3.client("bedrock-runtime", region_name=self.region)
            
            # Use Cohere Embed v4 with 1024 dimensions
            body = json.dumps({
                "texts": [text_chunk],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "output_dimension": 1024,
                "truncate": "END"
            })
            
            response = bedrock.invoke_model(
                body=body,
                modelId="cohere.embed-v4:0",
                accept="application/json",
                contentType="application/json"
            )
            
            response_body = json.loads(response.get("body").read())
            
            # Cohere v4 returns embeddings in format: {"embeddings": {"float": [[...]]}}
            embeddings_data = response_body.get("embeddings")
            if not embeddings_data:
                raise ValueError(f"No embedding in response. Full response: {response_body}")
            
            # Extract the embedding from the response
            if isinstance(embeddings_data, dict):
                embedding = embeddings_data.get("float", [[]])[0]
            else:
                embedding = embeddings_data[0]
            
            if not embedding:
                raise ValueError(f"Empty embedding returned. Response: {response_body}")
                
            print(f"Generated embedding with {len(embedding)} dimensions")
            logger.info(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            print(f"Failed to generate embedding: {str(e)}")
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise
    
    def search_similar_chunks(
        self,
        query_text: str,
        index_name: str = "sharepoint-docs",
        k: int = 25,
        filters: Optional[Dict[str, str]] = None
    ) -> List[Dict]:
        """
        Perform semantic search on OpenSearch using k-NN with optional filters.
        
        Args:
            query_text: The search query text
            index_name: Name of the OpenSearch index
            k: Number of results to return (default: 25)
            filters: Optional filters e.g., {"source": "filename.pdf", "rule_id": "123"}
        
        Returns:
            List[Dict]: List of search results with id, score, and source data
        
        Example:
            results = client.search_similar_chunks(
                query_text="What are the deorbit requirements?",
                filters={"source": "13.soa-deorbit-2023.pdf"}
            )
        """
        try:
            if not hasattr(self, 'client'):
                raise ValueError("OpenSearch client not initialized. Please provide host in __init__")
            print(self.client)
            print(f"index name: {index_name}, k: {k}, filters: {filters}")
            # Generate embedding for the query text
            print(f"Generating embedding for query: {query_text[:100]}...")
            logger.info(f"Generating embedding for query: {query_text[:100]}...")
            query_vector = self.get_embedding(query_text)
            
            # Build the query
            query_body = {
                "size": k,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "knn": {
                                    "vector_field": {
                                        "vector": query_vector,
                                        "k": k
                                    }
                                }
                            }
                        ]
                    }
                }
            }
            
            # Add filters if provided
            if filters:
                filter_clauses = []
                for field, value in filters.items():
                    filter_clauses.append({"term": {field: value}})
                query_body["query"]["bool"]["filter"] = filter_clauses
            
            # Execute search
            print(f"Executing k-NN search with k={k}, filters={filters}")
            logger.info(f"Executing k-NN search with k={k}, filters={filters}")
            response = self.client.search(index=index_name, body=query_body)
            
            # Parse results
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for hit in hits:
                results.append({
                    "id": hit.get("_id"),
                    "score": hit.get("_score"),
                    "text": hit.get("_source", {}).get("text"),
                    "source": hit.get("_source", {}).get("source"),
                    "file_id": hit.get("_source", {}).get("file_id"),
                    "rule_id": hit.get("_source", {}).get("rule_id"),
                    "sha": hit.get("_source", {}).get("sha"),
                    "sharepoint_url": hit.get("_source", {}).get("sharepoint_url"),
                    "modified_datetime": hit.get("_source", {}).get("modified_datetime")
                })
            
            print(f"Found {len(results)} results")
            logger.info(f"Found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"Failed to perform search: {str(e)}")
            logger.error(f"Failed to perform search: {str(e)}")
            raise
    
_default_client: SharePointClient | None = None

def _get_client() -> SharePointClient:
    """Get or create the default SharePoint client."""
    global _default_client
    if _default_client is None:
        _default_client = SharePointClient()
    return _default_client

@tool
def search_similar_chunks(
    query_text: str,
    index_name: str = "sharepoint-docs",
    k: int = 25,
    filters: Optional[Dict[str, str]] = None
) -> List[Dict]:
    client = _get_client()
    return client.search_similar_chunks(
        query_text=query_text,
        index_name=index_name,
        k=k,
        filters=filters
    )