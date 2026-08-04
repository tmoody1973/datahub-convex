# Copyright 2026 Radio Milwaukee / Liner Notes contributors
# SPDX-License-Identifier: Apache-2.0
"""Convex ingestion source for DataHub.

Discovers every table in one or more Convex deployments via the streaming
export REST API and emits, per deployment, a container and, per table, a
dataset with schema fields (mapped from Convex's JSON Schema), descriptions,
and an exact row-count profile.

Recipe example (deploy keys resolved from environment variables):

    source:
      type: convex
      config:
        deployments:
          - name: my-app-prod
            url: https://happy-animal-123.convex.cloud
            deploy_key: ${CONVEX_DEPLOY_KEY}
    sink:
      type: datahub-rest
      config:
        server: http://localhost:8080
"""

import json
import time
from typing import Any, Dict, Iterable, List, Tuple

from pydantic import Field

from datahub.configuration.common import ConfigModel
from datahub.emitter.mce_builder import make_data_platform_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.mcp_builder import ContainerKey, add_dataset_to_container, gen_containers
from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.api.decorators import (
    SourceCapability,
    SupportStatus,
    capability,
    config_class,
    platform_name,
    support_status,
)
from datahub.ingestion.api.source import Source, SourceReport
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.metadata.schema_classes import (
    ArrayTypeClass,
    BooleanTypeClass,
    DatasetProfileClass,
    DatasetPropertiesClass,
    NullTypeClass,
    NumberTypeClass,
    OtherSchemaClass,
    RecordTypeClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StatusClass,
    StringTypeClass,
    SubTypesClass,
    UnionTypeClass,
)

from datahub_convex.client import ConvexStreamingExportClient

PLATFORM = "convex"

# Convex bookkeeping fields present in every streaming-export document but
# not part of the user-defined table schema.
SYSTEM_FIELDS = {"_table", "_component", "_ts", "_deleted"}


class ConvexDeploymentConfig(ConfigModel):
    name: str = Field(description="Human-readable deployment name (used in dataset URNs and the container).")
    url: str = Field(description="Deployment URL, e.g. https://happy-animal-123.convex.cloud")
    deploy_key: str = Field(description="Deploy key for the deployment. Read-only scope (deployment:data:view) is sufficient. Reference an env var: ${MY_DEPLOY_KEY}")


class ConvexSourceConfig(ConfigModel):
    deployments: List[ConvexDeploymentConfig] = Field(description="Convex deployments to ingest.")
    env: str = Field(default="PROD", description="DataHub environment for dataset URNs.")
    include_row_counts: bool = Field(default=True, description="Count rows per table via list_snapshot and emit a datasetProfile aspect.")
    max_count_pages: int = Field(default=200, description="Safety cap on list_snapshot pages (~1024 rows each) per table when counting rows.")


class ConvexDeploymentKey(ContainerKey):
    deployment: str


def map_json_schema_field(name: str, prop: Dict[str, Any]) -> SchemaFieldClass:
    """Map one JSON Schema property to a DataHub SchemaField."""
    json_type = prop.get("type")
    if "anyOf" in prop:
        variants = [v.get("type", "object") for v in prop["anyOf"]]
        field_type: Any = UnionTypeClass()
        native = f"anyOf({', '.join(str(v) for v in variants)})"
    elif json_type == "string":
        field_type = StringTypeClass()
        native = "string"
    elif json_type in ("number", "integer"):
        field_type = NumberTypeClass()
        native = str(json_type)
    elif json_type == "boolean":
        field_type = BooleanTypeClass()
        native = "boolean"
    elif json_type == "object":
        field_type = RecordTypeClass()
        native = "object"
    elif json_type == "array":
        item_type = (prop.get("items") or {}).get("type", "any")
        field_type = ArrayTypeClass(nestedType=[str(item_type)])
        native = f"array<{item_type}>"
    else:
        field_type = NullTypeClass()
        native = str(json_type)

    return SchemaFieldClass(
        fieldPath=name,
        type=SchemaFieldDataTypeClass(type=field_type),
        nativeDataType=native,
        description=prop.get("$description"),
        nullable=False,  # required-ness handled below by caller
    )


def schema_fields_from_json_schema(table_schema: Dict[str, Any]) -> List[SchemaFieldClass]:
    properties: Dict[str, Any] = table_schema.get("properties", {})
    required = set(table_schema.get("required", []))
    fields = []
    for name, prop in properties.items():
        if name in SYSTEM_FIELDS:
            continue
        field = map_json_schema_field(name, prop)
        field.nullable = name not in required
        fields.append(field)
    return fields


@platform_name("Convex")
@config_class(ConvexSourceConfig)
@support_status(SupportStatus.INCUBATING)
@capability(SourceCapability.CONTAINERS, "One container per Convex deployment")
@capability(SourceCapability.SCHEMA_METADATA, "Table schemas discovered via the streaming export API")
@capability(SourceCapability.DESCRIPTIONS, "Document-reference fields carry Id(<table>) descriptions")
@capability(SourceCapability.DATA_PROFILING, "Exact row counts (optionally disabled)")
class ConvexSource(Source):
    """Ingests table metadata from Convex deployments.

    Uses Convex's streaming export REST API (available on every deployment;
    requires a deploy key) to discover tables, JSON schemas, and row counts.
    """

    def __init__(self, config: ConvexSourceConfig, ctx: PipelineContext):
        super().__init__(ctx)
        self.config = config
        self.report = SourceReport()

    @classmethod
    def create(cls, config_dict: dict, ctx: PipelineContext) -> "ConvexSource":
        return cls(ConvexSourceConfig.parse_obj(config_dict), ctx)

    def get_report(self) -> SourceReport:
        return self.report

    def get_workunits_internal(self) -> Iterable[MetadataWorkUnit]:
        for deployment in self.config.deployments:
            yield from self._ingest_deployment(deployment)

    def _ingest_deployment(self, deployment: ConvexDeploymentConfig) -> Iterable[MetadataWorkUnit]:
        client = ConvexStreamingExportClient(deployment.url, deployment.deploy_key)
        try:
            schemas = client.list_schemas()
        except Exception as e:
            self.report.report_failure(
                title="Cannot reach deployment",
                message="json_schemas request failed",
                context=f"{deployment.name} ({deployment.url}): {e}",
            )
            return

        container_key = ConvexDeploymentKey(
            platform=PLATFORM,
            deployment=deployment.name,
            env=self.config.env,
        )
        yield from gen_containers(
            container_key=container_key,
            name=deployment.name,
            sub_types=["Convex Deployment"],
            description=f"Convex deployment `{deployment.name}` at {deployment.url}",
        )

        for table, table_schema in sorted(schemas.items()):
            yield from self._ingest_table(deployment, client, container_key, table, table_schema)

    def _ingest_table(
        self,
        deployment: ConvexDeploymentConfig,
        client: ConvexStreamingExportClient,
        container_key: ConvexDeploymentKey,
        table: str,
        table_schema: Dict[str, Any],
    ) -> Iterable[MetadataWorkUnit]:
        dataset_urn = make_dataset_urn(
            platform=PLATFORM,
            name=f"{deployment.name}.{table}",
            env=self.config.env,
        )

        row_count: Tuple[int, bool] | None = None
        if self.config.include_row_counts:
            try:
                row_count = client.count_rows(table, self.config.max_count_pages)
            except Exception as e:
                self.report.report_warning(
                    title="Row count failed",
                    message="list_snapshot paging failed",
                    context=f"{deployment.name}.{table}: {e}",
                )

        custom_properties = {"deployment_url": deployment.url, "table": table}
        if row_count is not None:
            count, exact = row_count
            custom_properties["row_count"] = str(count) if exact else f"{count}+ (capped)"

        aspects: List[Any] = [
            StatusClass(removed=False),
            DatasetPropertiesClass(
                name=table,
                description=f"Convex table `{table}` in deployment `{deployment.name}`.",
                customProperties=custom_properties,
            ),
            SubTypesClass(typeNames=["Table"]),
            SchemaMetadataClass(
                schemaName=f"{deployment.name}.{table}",
                platform=make_data_platform_urn(PLATFORM),
                version=0,
                hash="",
                platformSchema=OtherSchemaClass(rawSchema=json.dumps(table_schema, indent=2)),
                fields=schema_fields_from_json_schema(table_schema),
            ),
        ]
        if row_count is not None:
            aspects.append(
                DatasetProfileClass(
                    timestampMillis=int(time.time() * 1000),
                    rowCount=row_count[0],
                    columnCount=len(
                        [k for k in table_schema.get("properties", {}) if k not in SYSTEM_FIELDS]
                    ),
                )
            )

        for aspect in aspects:
            yield MetadataChangeProposalWrapper(entityUrn=dataset_urn, aspect=aspect).as_workunit()

        yield from add_dataset_to_container(container_key=container_key, dataset_urn=dataset_urn)
