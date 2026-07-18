"""Launch pipeline stages."""

from slipp.services.launch.stages.ansible import (
    AppRolesStage,
    GroupVarsStage,
    PlaybookGenerationStage,
)
from slipp.services.launch.stages.caddy import CaddyConfigStage, CaddyRoleStage
from slipp.services.launch.stages.common import ValidationStage
from slipp.services.launch.stages.compose import ComposeGenerationStage
from slipp.services.launch.stages.dockerfile import DockerfileGenerationStage
from slipp.services.launch.stages.inventory import (
    InventoryFileStage,
    InventoryLoadStage,
    InventoryValidationStage,
)
from slipp.services.launch.stages.ports import PortResolutionStage
from slipp.services.launch.stages.proxy import ProxyResolutionStage
from slipp.services.launch.stages.registry import RegistrationStage, SummaryStage
from slipp.services.launch.stages.requirements import RequirementsFileStage
from slipp.services.launch.stages.scaffold import (
    ScaffoldInventoryStage,
    ScaffoldPromptStage,
    ScaffoldRegistrationStage,
    ScaffoldSummaryStage,
    ScaffoldValidationStage,
)
from slipp.services.launch.stages.scan import ProjectScanStage
from slipp.services.launch.stages.wg_manage import WgManageRoleStage

__all__ = [
    "ValidationStage",
    "ProjectScanStage",
    "InventoryLoadStage",
    "InventoryValidationStage",
    "InventoryFileStage",
    "PortResolutionStage",
    "ProxyResolutionStage",
    "DockerfileGenerationStage",
    "CaddyConfigStage",
    "CaddyRoleStage",
    "WgManageRoleStage",
    "PlaybookGenerationStage",
    "GroupVarsStage",
    "AppRolesStage",
    "RequirementsFileStage",
    "ComposeGenerationStage",
    "RegistrationStage",
    "SummaryStage",
    "ScaffoldValidationStage",
    "ScaffoldPromptStage",
    "ScaffoldInventoryStage",
    "ScaffoldRegistrationStage",
    "ScaffoldSummaryStage",
]
