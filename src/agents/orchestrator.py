from utils.logging_config import get_logger
from .base import BaseAgent
from .snow_agent import ServiceNowAgent
from tools.snow_tools import create_incident, search_incidents, delete_incident
logger = get_logger(__name__)

class OrchestratorAgent(BaseAgent):
        def __init__(self, model_id: str | None = None, region: str | None = None):
            self._servicenow_agent: ServiceNowAgent | None = None

            self._agent_reports: list[dict] = []

            super().__init__(
                agent_type="orchestrator",
                model_id=model_id,
                region=region,
            )

        def get_tools(self) -> list:
            return [create_incident, search_incidents, delete_incident]
        
        @property
        def snow_agent(self) -> ServiceNowAgent:
            if self._servicenow_agent is None:
                logger.info("Initializing ServiceNow agent within Orchestrator")
                self._servicenow_agent = ServiceNowAgent(model_id=self.model_id, region=self.region)
            return self._servicenow_agent
        
        def get_actions(self) -> list[dict]:
            actions_list = []
            
            for action in self.action_history:
                actions_list.append(
                    {
                        "agent": "Orchestrator",
                        **action.model_dump(),
                    }
                )

            if self._servicenow_agent:
                for action in self._servicenow_agent.action_history:
                    actions_list.append(
                        {
                            "agent": "ServiceNow",
                            **action.model_dump(),
                        }
                    )
                    

            return actions_list
