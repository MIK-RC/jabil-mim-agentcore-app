from .base import BaseAgent
from property.spclient import (SharePointClient, search_similar_chunks)


class SharePointAgent(BaseAgent):
    def __init__(self, model_id: str | None = None, region: str | None = None, opensearch_host: str | None = None):
        """
        Initialize SharePoint Agent.
        
        Args:
            model_id: Optional model ID to override config
            region: AWS region for AOSS (default: 'us-east-1')
            opensearch_host: OpenSearch Serverless endpoint (without https://)
        """
        # Initialize SharePoint client with AOSS connection
        self._spclient = SharePointClient(
            region=region or 'us-east-1',
            host=opensearch_host
        )
        print("SharePointAgent initialized with SharePointClient.")
        
        # Initialize base agent with correct agent_type to match config
        super().__init__(agent_type="sharepoint_search", model_id=model_id, region=region)

    def get_tools(self) -> list:
        """Return list of tools available to this agent."""
        return [search_similar_chunks]
        
       
