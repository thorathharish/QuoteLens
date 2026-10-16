"""One-click demo projects from the sample BOMs (guided demo for first-time viewers)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from app.domain.enums import DataMode, DemoRole
from app.domain.errors import NotFoundError
from app.domain.ids import new_id
from app.domain.models import Job, Project
from app.infra.repositories import Repositories
from app.ingestion.service import IngestionService


class Scenario(StrEnum):
    MOTOR_CONTROLLER = "motor_controller"
    IOT_SENSOR = "iot_sensor"
    MESSY_FORMAT = "messy_format"


_SCENARIOS: dict[Scenario, tuple[str, str]] = {
    Scenario.MOTOR_CONTROLLER: ("motor_controller.xlsx", "MC48 BLDC motor controller (demo)"),
    Scenario.IOT_SENSOR: ("iot_sensor.csv", "IoT sensor node (demo)"),
    Scenario.MESSY_FORMAT: ("messy_format.xlsx", "Drive interface board: messy export (demo)"),
}
TARGET_SHIP_DAYS = 56


@dataclass
class DemoService:
    repos: Repositories
    ingestion: IngestionService
    samples_dir: Path

    async def seed(self, scenario: Scenario, role: DemoRole) -> tuple[Project, Job]:
        filename, name = _SCENARIOS[scenario]
        path = self.samples_dir / filename
        if not path.is_file():
            raise NotFoundError(f"Sample file {filename} is not available on this server")
        project = Project(
            id=new_id("prj"),
            name=name,
            customer="Demo customer",
            currency="USD",
            build_quantities=[100, 1000, 5000],
            target_ship_date=(datetime.now(UTC) + timedelta(days=TARGET_SHIP_DAYS)).date(),
            data_mode=DataMode.DEMO_SNAPSHOT,  # a demo never depends on live APIs
        )
        await self.repos.projects.put(project)
        upload = await self.ingestion.upload(project.id, filename, path.read_bytes())
        job = await self.ingestion.confirm_mapping(project.id, upload.id, [], role)
        return await self.repos.projects.get(project.id), job
