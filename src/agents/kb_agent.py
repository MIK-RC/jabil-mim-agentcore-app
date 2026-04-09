from .base import BaseAgent
from tools.kb_tools import (KnowledgeBaseClient, search_similar_chunks)


class KnowledgeBaseAgent(BaseAgent):
    def __init__(self, model_id: str = "", region: str = "", opensearch_host: str = ""):
        """
        Initialize KnowledgeBase Agent.
        
        Args:
            model_id: Optional model ID to override config
            region: AWS region for AOSS (default: 'us-east-1')
            opensearch_host: OpenSearch Serverless endpoint (without https://)
        """        
        # Initialize KnowledgeBase client with AOSS connection
        self._kbclient = KnowledgeBaseClient(
            region=region,
            host=opensearch_host
            )        
        
        super().__init__(agent_type="knowledge_base_search", model_id=model_id, region=region)

    def get_tools(self) -> list:
        """Return list of tools available to this agent."""
        return [search_similar_chunks]
        
       
