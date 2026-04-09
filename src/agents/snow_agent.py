from tools.snow_tools import (
    ServiceNowClient,
    # create_incident,
    get_incident_status,
    search_incidents,
    update_incident,
    delete_incident
)
from .base import BaseAgent


class ServiceNowAgent(BaseAgent):
    def __init__(self, model_id: str = "", region: str = "", instance: str = "", username: str = "", password: str = "",):
        self._snowclient = ServiceNowClient(instance=instance, username=username, password=password)
        
        super().__init__(agent_type="servicenow", model_id=model_id, region=region)

    def get_tools(self) -> list:
        return [update_incident, get_incident_status, search_incidents, delete_incident]
        # return [create_incident, update_incident, get_incident_status, search_incidents, delete_incident]
